<p align="center">
  <img src="media/neo-kobe.png" width="100%" alt="Snatcher for Sega Saturn beside the Neo Kobe skyline at night">
</p>

# Snatcher for Sega Saturn

## Why port Snatcher to a console that already had it?

Konami released *Snatcher* for the Saturn in Japan in 1996. That edition paired the Japanese PC Engine voice performances with redrawn artwork and rearranged music. [Sega’s Saturn release catalog](https://www.sega.jp/history/hard/segasaturn/software_l.html)

This port is for people who want to play the *Sega CD* edition on a Saturn. When Gillian walks into JUNKER headquarters, you hear Mika greet him in English. You get the Sega CD artwork and soundtrack, and the extra conversations from its expanded third act. The port reads those performances, pictures and songs from your US Sega CD disc and plays them as a native Saturn game.

[**Patch your US Sega CD disc in your browser →**](https://t3chnaztea.github.io/snatcher-saturn/)

**All three acts completed in Beetle Saturn. Physical Saturn, SAROO and CRT Stunner tests are pending.**

<p align="center">
  <a href="media/gameplay.mp4"><img src="media/gameplay.gif" width="512" alt="Mika greets Gillian, Gillian inspects his turbocycle, then fires at Insectors in the factory"></a>
</p>

*Beetle Saturn capture.* Mika at JUNKER headquarters, a parking lot investigation and the first factory shootout. [Watch the 20-second clip with sound](media/gameplay.mp4).

## Patch your disc

[**Open the Snatcher Saturn Patcher**](https://t3chnaztea.github.io/snatcher-saturn/) in desktop Chrome. Your disc files stay on your computer.

1. Choose the CUE and all its BIN files from your original US Sega CD copy of *Snatcher* (T-95035). Both a combined BIN and 21 split tracks are supported.
2. Leave the boxes unchecked for US retail, or pick any of the restorations below. Select **Create Saturn disc**.
3. Download **both** `snatcher-saturn.bin` and `snatcher-saturn.cue` into the same folder. Open the CUE in Beetle Saturn or copy the pair to your SAROO card.

The patcher verifies the data track, all 20 audio tracks and both output files. A split dump with missing pregaps gets silent padding to preserve retail track timing. The one non-silent retail pregap sector requires a dump with stored pregaps.

### Optional Uncut restorations

| Patcher choice | What changes |
| --- | --- |
| Outer Heaven costumes | Restores the PC Engine costumes in the club’s wide shot. The close-up portraits keep their US artwork. |
| Lisa’s apartment artwork | Restores the Room 202 illustration after the fight. |
| Database dates | Changes the in-game database dates to the Uncut chronology. |

![The Outer Heaven stage with US retail patrons on the left and restored costumes on the right](media/outer-heaven.png)

These choices come from [Snatcher Uncut](https://github.com/t3chnaztea/snatcher-uncut-segacd).

## Controls and Beetle Saturn setup

Configure your US/EU Saturn BIOS in the frontend’s system directory. Load the generated CUE with Beetle Saturn. Set port 1 to a control pad. Press Start or C for New Game. Press Start during the opening to skip to Act 1. Use Up and Down to highlight a command, C to confirm or advance dialogue, and B to return. In a shooting encounter, press A to draw. Hold a direction to aim or release the D-pad to aim at the center. Press C to fire.

For a light gun, keep the pad on port 1. Set port 2 to **Stunner**. Bind aim and trigger in your frontend. Pull the trigger to draw and fire. An off-screen shot counts as a miss. Use the port 1 pad again for dialogue.

## Play on SAROO

On a working SAROO card, create `SAROO/ISO/Snatcher Saturn`. Copy both generated disc files there under their original names. Run the following command in that directory. Compare both hashes with the patcher’s verified checksums before ejecting the card.

```sh
shasum -a 256 snatcher-saturn.bin snatcher-saturn.cue
```

Build the standalone Stunner Probe with `bash tools/build_stunner_probe.sh`.

Select the game in the SAROO loader. For a smoke test, start New Game, listen for the Act 1 announcement and advance Mika’s greeting. At the parking lot, inspect the turbocycle body. Choose **Use Metal Gear → Save** and wait for confirmation. Reset the console. Select **Continue** and load that slot. Verify the parking lot returns and the second inspection skips the manufacturer line.

For the physical gun test, connect the pad to port 1 and the Stunner to port 2 before boot. Use a compatible CRT. Open **Stunner Probe** from SAROO. Shoot each of the nine white dots. Each intended field should turn green. Hold the trigger on one dot. The marker below the grid should move once. Aim away from the screen and fire. The highlight should clear and the marker should turn red. In the game, finish a shooting encounter and advance dialogue with the pad. Record the gun model, CRT model, console region, SAROO firmware and both disc hashes with the result.

## Test coverage and known issues

Desktop Chrome produced verified BIN and CUE downloads from the public patcher for all eight restoration combinations. Tests included combined and split dumps, with both stored and omitted audio pregaps.

The 4:36:42 playthrough started with empty backup RAM and used zero emulator state loads across 993,212 frames. All 23 story checkpoints matched the earlier development route. All 14 additional whole-screen checks matched the current build. The final Junker logo matched the independently recorded ending.

Beetle passed 50 pad and Stunner cases across 11 shooting encounters on the staged image. The emulated Stunner scored 64 hits in the first Act 3 corridor and 40 in the second. Off-screen shots missed. Holding the trigger fired once.

Beetle restored the parking lot investigation after a reset and a separate cold boot. All four save slots loaded. Declining an overwrite preserved every backup byte. An Act 2 headquarters save also survived a reset.

All 1,162 streamed voice cues matched the original disc across 81,283,392 decoded samples. The full playthrough passed all 210 staff-roll music checks.

The opening matched the US music in all 162 sample windows. Within a ten-frame timing window, six of 88 opening pictures and six of 114 credits pictures differed from their references. Five of the six credits pictures matched between 11 and 37 frames away. One still differed within 90 frames.

[Verified playthrough hashes](playthrough-receipt.json) · [Recorded controller inputs](tools/routes/full-campaign.pad)

### Build verification

A clean build from the combined US BIN reproduced the tested BIN and CUE. The retail BIN SHA-256 is `53810d2dd8814b9545e145ade6e5e0bd4414a5635ea439a042eb0f66239ca2f9`.

A clean build with all three switches changed six of 912 Saturn disc files. Both restored pictures matched their expected hashes. Only two of 39 script text pools changed. All 20 audio tracks matched retail.

Each switch also passed in a separate build. The date switch changed only two script modules. The bar switch changed the Outer Heaven artwork, its lighting map and the executable. The Lisa switch changed the apartment artwork and its transfer data. Each preserved all 20 playable audio tracks.

<details>
<summary>Developer build from source</summary>

This build uses the adjacent `snatcher-uncut` and `sonic-cd-saturn` projects on the development Mac. It requires Python 3, Uncut’s installed Python environment and US Sega CD BIOS, the local Genesis Plus GX core, Sonic’s installed Yaul toolchain and its generated CD and sound driver files. The host build also uses a C compiler, GNU Make (`gmake`), `xorrisofs`, libpng, liblz4 and pkg-config. Run this command from the port directory. Choose an output directory that does not exist.

```sh
python3 tools/patcher.py "/path/to/Snatcher.cue" "./Saturn build"
```

The output contains `snatcher-saturn.bin`, `snatcher-saturn.cue` and `build-receipt.json`. Keep the BIN and CUE together. The receipt records your patch choices and output hashes.

For restorations, add `--bar-background`, `--lisa-art` or `--database-dates` before the source CUE. The artwork switches require `xdelta3` and the Uncut v0.11.0-rc1 component package. The default registry is `../snatcher-uncut/build/m9/release-v1/profiles.json`. Use `--uncut-registry "/path/to/profiles.json"` to select another copy.

</details>
