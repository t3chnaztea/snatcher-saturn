'use strict';
const $ = id => document.getElementById(id);
let worker = null, files = [], urls = [];
function clearResult() {
  $('downloads').hidden = true;
  for (const url of urls) URL.revokeObjectURL(url);
  urls = [];
  for (const id of ['bin','cue']) $(id).removeAttribute('href');
  $('progressBox').hidden = true;
}
function choose(list) {
  clearResult();
  files = Array.from(list);
  const cue = files.find(file => /\.cue$/i.test(file.name));
  $('selection').textContent = files.length ? [cue?.name, files.length + ' files selected'].filter(Boolean).join(' · ') :
    'US retail T-95035 · One combined BIN or 21 split tracks';
}
function report(message, progress, error = false) {
  $('progressBox').hidden = false;
  $('status').textContent = message;
  $('status').classList.toggle('error',error);
  $('progress').hidden = error || progress === 100;
  $('progress').value = progress;
}
function stop() {
  worker?.terminate();
  worker = null;
  for (const field of document.querySelectorAll('fieldset')) field.disabled = false;
  $('create').disabled = false;
  $('cancel').hidden = true;
}
$('files').onchange = event => choose(event.target.files);
for (const id of ['bar','lisa','dates']) $(id).onchange = clearResult;
$('drop').ondragover = event => { event.preventDefault(); $('drop').classList.add('over'); };
$('drop').ondragleave = () => $('drop').classList.remove('over');
$('drop').ondrop = event => {
  event.preventDefault();
  $('drop').classList.remove('over');
  if (!worker) choose(event.dataTransfer.files);
};
$('cancel').onclick = () => { stop(); report('Cancelled. Your source files are unchanged.',100); };
$('patcher').onsubmit = event => {
  event.preventDefault();
  if (worker) return;
  clearResult();
  if (!files.length) {
    report('Choose the CUE and BIN files from your US Sega CD disc first.', 0, true);
    $('files').focus();
    return;
  }
  const art = $('bar').checked ? ($('lisa').checked ? 'both' : 'bar') : ($('lisa').checked ? 'lisa' : 'retail');
  const key = art + ($('dates').checked ? '-dates' : '');
  $('create').disabled = true;
  $('cancel').hidden = false;
  for (const field of document.querySelectorAll('fieldset')) field.disabled = true;
  report('Reading disc layout…', 1);
  try {
    worker = new Worker('worker.js');
    worker.onerror = () => { stop(); report('The patcher could not finish. Use a current desktop browser and try again.', 0, true); };
    worker.onmessage = ({data}) => {
      if (data.error) { stop(); report(data.error, 0, true); }
      else if (data.result) {
        stop();
        const result = data.result;
        for (const id of ['bin','cue']) {
          const url = URL.createObjectURL(result[id]);
          urls.push(url);
          $(id).href = url;
        }
        $('hashes').textContent = result.binHash + '  snatcher-saturn.bin\n' + result.cueHash + '  snatcher-saturn.cue';
        $('downloads').hidden = false;
        report('Saturn BIN and CUE verified.',100);
      } else report(data.message,data.progress);
    };
    worker.postMessage({files, key});
  } catch (err) { stop(); report(err.message,0,true); }
};
