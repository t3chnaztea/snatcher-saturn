include $(YAUL_INSTALL_ROOT)/share/build.pre.mk
SH_PROGRAM := snatcher-saturn
SH_SRCS := src/main.c src/credits.c src/save.c src/practice.c src/lightgun.c src/flashlight.c src/street.c src/disc.c src/drive.c src/crash.c src/crash_graphics.c src/city.c src/plaza.c src/report.c src/scan.c src/voice.c src/fm.c build/sound/ponesound.c src/reception.c src/script.c src/panel.c src/gfx.c
SH_BUILD_DIR := build/saturn
SH_OUTPUT_DIR := dist
SH_SRCS += build/cd-block/cd-block_cmds.c
# Yaul adds the first-read binary and three text files when it creates the ISO.
ISO_BOOT_FILES := cd/A.BIN cd/ABS.TXT cd/BIB.TXT cd/CPY.TXT
ISO_ROOT_FILES := $(sort $(wildcard cd/*) $(ISO_BOOT_FILES))
SH_CFLAGS += -DDISC_ROOT_CAPACITY=$(words $(ISO_ROOT_FILES))
SH_CFLAGS += -Os -Ibuild/sound -Ibuild -Ibuild/cd-block
BUILTIN_ASSETS += build/sound/driver.bin;sound_driver build/names.bin;speaker_names build/font.bin;script_font
IP_VERSION := V0.138
IP_RELEASE_DATE := 20261122
IP_AREAS := JTUBKAEL
IP_PERIPHERALS := J
IP_TITLE := SNATCHER SATURN
IP_MASTER_STACK_ADDR := 0x06004000
IP_SLAVE_STACK_ADDR := 0x06001E00
IP_1ST_READ_ADDR := 0x06004000
IP_1ST_READ_SIZE := 0
AUDIO_TRACKS_DIRECTORY := build/audio-tracks
include $(YAUL_INSTALL_ROOT)/share/build.post.iso-cue.mk

$(SH_OUTPUT_PATH)/$(SH_PROGRAM).iso: cd/BRIEF8.BIN cd/BRIEF9.BIN cd/BRIEFING.BIN cd/CHASEIN.BIN cd/CHASE10.BIN cd/CRASH11.BIN cd/CRASHTIL.BIN cd/CARDEST.BIN cd/COCKPIT.BIN $(wildcard cd/CAB*.BIN) cd/CARACCEL.BIN cd/CARROAD.BIN $(wildcard cd/ROAD*.BIN) cd/STREET.BIN cd/ACT1END.BIN cd/A3CD15.BIN cd/A3CD16.BIN cd/A3CD17.BIN cd/A3CD18.BIN cd/PRO0.BIN cd/PRO1.BIN cd/CREDITS.BIN cd/A3M8C2.BIN $(wildcard cd/A3TAKE*.BIN cd/A3V*.BIN cd/A3D?.BIN) cd/A3CANOPY.BIN cd/A3BOARD.BIN cd/A3EXIT.BIN cd/A3CHURCH.BIN cd/A3REVEAL.BIN cd/A3OPEN.BIN cd/A3AISLE.BIN cd/A3PAN.BIN cd/A3SMALL.BIN cd/A3LARGE.BIN cd/A3OUT.BIN $(wildcard cd/A3D???.BIN) cd/A3CYL.BIN cd/A3RETURN.BIN cd/A3DOOR.BIN cd/A3DOOR2.BIN cd/SWARM.BIN cd/FINAL13.BIN cd/FINAL14.BIN cd/A3FAILIN.BIN cd/A3FAILFX.BIN cd/A3RIN.BIN $(wildcard cd/A3RDOOR*.BIN cd/A3RHALL*.BIN) $(wildcard cd/A3E???.BIN) cd/A3ENDIN.BIN cd/A3ENDTWO.BIN $(wildcard cd/A3E1*.BIN cd/A3DC99*.BIN cd/A3DCF0*.BIN) cd/A3HALL2.BIN cd/A3RFADE.BIN cd/A3CULT.BIN cd/A3REAR.BIN cd/A3REARID.BIN cd/A3FRAME.BIN cd/A3BACK.BIN cd/A3CRUISE.BIN cd/A3LAND.BIN cd/A3CDIN.BIN cd/A3CDOUT.BIN cd/ACT3ROOM.BIN cd/ACT3LAMP.BIN cd/ACT3FADE.BIN cd/ACT3CITY.BIN cd/ACT3IN.BIN cd/CUREIN.BIN cd/CUREOUT.BIN cd/ACT1.BIN cd/IDCARD.BIN cd/FACTPCM.BIN cd/DRIP.BIN cd/SHADOW.BIN cd/RESIDENT.BIN $(wildcard cd/FM*.BIN) cd/HAIR.BIN cd/SKIN.BIN cd/ORGANIC.BIN cd/VOICE.BIN cd/MIX.BIN cd/RANGEPCM.BIN cd/NAVPCM.BIN cd/GUNPCM.BIN cd/CARPCM.BIN cd/PLAZA.BIN cd/PLAZAB.BIN cd/IVANDOOR.BIN $(wildcard cd/FC*.BIN cd/FG*.BIN cd/FR*.BIN) cd/GDOOR.BIN cd/GENTRY.BIN cd/G2DOOR.BIN cd/G2ENTRY.BIN cd/MIKACALL.BIN cd/MIKATGT.BIN cd/MFIGHT.BIN cd/RESCIN.BIN cd/RESC13.BIN cd/RESC14.BIN cd/RESCOUT.BIN cd/APTNEON.BIN cd/QLIGHT.BIN cd/QROOM1.BIN cd/QROOM2.BIN cd/QROOM3.BIN cd/QBUTTON.BIN cd/QHATCH.BIN cd/QATTACK.BIN cd/QHEAD.BIN cd/QGREEN.BIN cd/TUNDARK.BIN cd/TUNLAMP.BIN cd/TUNIDLE.BIN cd/TUNEXIT.BIN cd/TUNWALK.BIN cd/TAXIRIDE.BIN cd/TAXITURN.BIN cd/TUNLADR.BIN cd/TUNHIDE.BIN cd/TUNBATH.BIN $(wildcard cd/TUN6*.BIN cd/TUN7*.BIN) cd/VIS21.BIN $(wildcard cd/QVIS*.BIN cd/QRC*.BIN) cd/QLAB.BIN cd/QLABOUT.BIN cd/QTALK.BIN cd/QREACH.BIN cd/QFALL.BIN cd/QFIGHT.BIN cd/QSTAIRS.BIN cd/QDOOR.BIN cd/QENTRY.BIN cd/APTDOOR.BIN cd/APTLIGHT.BIN cd/APTROOM.BIN cd/APTSHOW.BIN cd/APTTALK.BIN cd/APT70.BIN $(wildcard cd/LIST*.BIN) $(wildcard cd/GTERM*.BIN) cd/DRIVE.BIN cd/TRANSIT.BIN cd/RETURN.BIN cd/STORM.BIN cd/PHONE.BIN cd/PHONEUI.BIN cd/PHONENAP.BIN cd/CHOFFICE.BIN cd/CHPHOTO.BIN cd/CHFRAME.BIN cd/NAPCALL.BIN $(wildcard cd/BENSON*.BIN) cd/NAPSHOW.BIN cd/NAPTALK.BIN cd/PHONEOFF.BIN cd/SHOPFX.BIN cd/BLASTER.BIN $(wildcard cd/DATA_*.BIN) $(wildcard cd/SP??.BIN)

# The root entry count is compiled into the ISO reader.
$(call macro-convert-build-path,src/disc.o): cd Makefile
