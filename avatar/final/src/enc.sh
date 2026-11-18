#!/bin/zsh
# enc.sh FRAMEDIR FPS OUT.mp4 — Telegram animated avatar: H.264 High, yuv420p BT.601 limited range (Telegram cuts the chat-list still as BT.601: a BT.709 video came back washed out, #2AABEE as #34B1E7, 2026-11-18; tagged in the
# container and the stream VUI), one closed GOP over the whole loop (keyint = frame count), -tune animation, CRF 14
# for the motion; the rest frames (the exact cover) at QP 4 through x264 zones (render_a.py zones FPS), so the still
# part of the loop is near-lossless and does not shimmer. Level 4.0 for 30 fps, 4.2 for 60 fps.
D=${0:A:h}; N=$(ls $1/*.png | wc -l | tr -d ' '); L=4.0; [[ $2 -gt 30 ]] && L=4.2
Z=$(${PY:-python3} $D/render_a.py zones $2)   # PY = a python with pycairo + numpy + pillow
ffmpeg -v error -y -framerate $2 -i $1/%04d.png \
  -vf "scale=out_color_matrix=bt601:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p" \
  -c:v libx264 -preset veryslow -tune animation -crf 14 -profile:v high -level $L -g $N -keyint_min $N -sc_threshold 0 \
  -x264-params "open-gop=0:colorprim=smpte170m:transfer=smpte170m:colormatrix=smpte170m:zones=$Z" \
  -colorspace smpte170m -color_primaries smpte170m -color_trc smpte170m -color_range tv -movflags +faststart -an $3
