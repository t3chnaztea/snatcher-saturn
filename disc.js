// A US retail dump has one Mode 1 data track and twenty CD audio tracks.
const RAW_SECTOR = 2352;
const DATA_SECTOR = 2048;

function sectors(time) {
  const match = /^(\d+):([0-5]\d):([0-7]\d)$/.exec(time);
  if (!match || Number(match[3]) >= 75) throw Error('Invalid CUE time: ' + time);
  return (Number(match[1]) * 60 + Number(match[2])) * 75 + Number(match[3]);
}

function timecode(n) {
  return [Math.floor(n / 4500), Math.floor(n / 75) % 60, n % 75]
    .map(value => String(value).padStart(2, '0')).join(':');
}

function readCue(text, selected) {
  const files = new Map();
  for (const file of selected) {
    const key = file.name.toLowerCase();
    if (files.has(key)) throw Error('Duplicate filename: ' + file.name);
    files.set(key, file);
  }
  const tracks = [], used = new Set();
  let file, track;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || /^(REM|TITLE|PERFORMER|SONGWRITER|CATALOG|ISRC|FLAGS)\b/i.test(line)) continue;
    let match;
    if ((match = /^FILE\s+"([^"\\/:]+)"\s+BINARY$/i.exec(line))) {
      if (file && !track) throw Error('CUE file has no track: ' + file.name);
      file = files.get(match[1].toLowerCase());
      if (!file) throw Error('Select the BIN named in the CUE: ' + match[1]);
      if (used.has(file) || !file.size || file.size % RAW_SECTOR) throw Error('Invalid BIN: ' + file.name);
      used.add(file);
      track = null;
    } else if ((match = /^TRACK\s+(\d\d)\s+(MODE1\/2352|AUDIO)$/i.exec(line)) && file) {
      const number = tracks.length + 1;
      if (Number(match[1]) !== number || match[2].toUpperCase() !== (number === 1 ? 'MODE1/2352' : 'AUDIO')) {
        throw Error('Expected Track 01 MODE1/2352 followed by audio Tracks 02 through 21.');
      }
      track = {number, file};
      tracks.push(track);
    } else if ((match = /^INDEX\s+(00|01)\s+(\S+)$/i.exec(line)) && track) {
      const field = match[1] === '00' ? 'gapStart' : 'play';
      if (track.play !== undefined || track[field] !== undefined) throw Error('Duplicate or misordered index: ' + line);
      track[field] = sectors(match[2]);
    } else if ((match = /^PREGAP\s+(\S+)$/i.exec(line)) && track &&
               track.pregap === undefined && track.play === undefined && track.gapStart === undefined) {
      track.pregap = sectors(match[1]);
    } else throw Error('Unsupported CUE line: ' + line);
  }
  if (!track || tracks.length !== 21 || ![1, 21].includes(used.size)) {
    throw Error('Select a US Snatcher CUE with one combined BIN or 21 separate BIN tracks.');
  }
  if (files.size !== used.size) throw Error('Select only the BIN files listed in this CUE.');
  for (const [index, t] of tracks.entries()) {
    t.start = t.gapStart ?? t.play;
    const next = tracks[index + 1];
    t.end = next?.file === t.file ? (next.gapStart ?? next.play) : t.file.size / RAW_SECTOR;
    if (!Number.isInteger(t.play) || t.play >= t.end || t.play < t.start ||
        (t.gapStart !== undefined && (t.start >= t.play || t.pregap !== undefined)) ||
        (used.size === 21 && t.start !== 0) || (used.size === 1 && t.pregap !== undefined)) {
      throw Error('Invalid track boundaries on Track ' + t.number);
    }
  }
  if (tracks[0].play !== 0 || tracks[0].pregap !== undefined || tracks[0].gapStart !== undefined) throw Error('Invalid data track index.');
  return tracks;
}

function makeDictionary(raw, manifest) {
  const size = manifest.sourceSectors * DATA_SECTOR;
  const dict = new Uint8Array(size + manifest.voiceBytes);
  for (let i = 0; i < manifest.sourceSectors; i++) {
    const offset = i * RAW_SECTOR + 16;
    dict.set(raw.subarray(offset, offset + DATA_SECTOR), i * DATA_SECTOR);
  }
  // Sega CD voice samples use sign/magnitude. Saturn SCSP samples use signed PCM.
  const translation = Uint8Array.from({length: 256}, (_, n) => n >= 128 ? n - 128 : -n);
  for (let i = 0; i < manifest.voiceBytes; i++) dict[size + i] = translation[dict[manifest.voiceOffset + i]];
  return dict;
}

// CD-ROM Mode 1 EDC and two interleaved Reed-Solomon parity codes.
function encodeTrack(iso) {
  if (iso.length % DATA_SECTOR) throw Error('Partial ISO sector.');
  const edcTable = new Uint32Array(256), forward = new Uint8Array(256), inverse = new Uint8Array(256);
  for (let i = 0; i < 256; i++) {
    let crc = i;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ (crc & 1 ? 0xd8018001 : 0);
    edcTable[i] = crc;
    forward[i] = (i << 1) ^ (i & 128 ? 0x11d : 0);
    inverse[i ^ forward[i]] = i;
  }
  const output = new Uint8Array(iso.length / DATA_SECTOR * RAW_SECTOR);
  function parity(base, majors, minors, majorStep, stride, dest) {
    const size = majors * minors;
    for (let m = 0; m < majors; m++) {
      let index = (m >>> 1) * majorStep + (m & 1), a = 0, b = 0;
      for (let n = 0; n < minors; n++) {
        const value = output[base + index];
        a = forward[a ^ value]; b ^= value;
        index += stride;
        if (index >= size) index -= size;
      }
      const p = inverse[forward[a] ^ b];
      output[dest + m] = p;
      output[dest + majors + m] = p ^ b;
    }
  }
  const bcd = n => (Math.floor(n / 10) << 4) | (n % 10);
  for (let offset = 0, n = 0; offset < output.length; offset += RAW_SECTOR, n++) {
    output.fill(255, offset + 1, offset + 11);
    const address = n + 150;
    output[offset + 12] = bcd(Math.floor(address / 4500));
    output[offset + 13] = bcd(Math.floor(address / 75) % 60);
    output[offset + 14] = bcd(address % 75);
    output[offset + 15] = 1;
    output.set(iso.subarray(n * DATA_SECTOR, (n + 1) * DATA_SECTOR), offset + 16);
    let crc = 0;
    for (let i = offset; i < offset + 2064; i++) crc = (crc >>> 8) ^ edcTable[(crc ^ output[i]) & 255];
    for (let i = 0; i < 4; i++) output[offset + 2064 + i] = crc >>> (8 * i);
    parity(offset + 12, 86, 24, 2, 86, offset + 2076);
    parity(offset + 12, 52, 43, 86, 88, offset + 2248);
  }
  return output;
}
