"""Feed (@FeedChannelsBot) animated avatar, variant А «Пост уходит вправо», final.
The loop's rest frame IS the static avatar (cover.svg written by this script draws the same thing).

Drawing (640-unit space): Telegram logo gradient #2AABEE -> #229ED9; back card 240 x 210 at BACK_A opacity showing PEEK
above the front card 300 x 210; radius 36; Telegram Web A's filled forward icon (share-filled.svg, 32-unit grid) at
scale 5.8 on the front card, placed as in the first static draft (translate 224.387, 246.939 for a front card at 170, 235).

Motion (seconds; loop LOOP s, rest = the exact cover outside [T0, T_END]):
  old front   slides right 480 and leaves the frame: Telegram iOS slide curve mirrored (accelerating; starts at ~0 speed)
  old back -> front, arrow arriving from the left, next back card rising from behind: Telegram iOS spring
  (CASpringAnimation mass 5, stiffness 900, damping 100, initial velocity 0: Display/CAAnimationUtils.swift), so
  every arrival starts from rest with zero speed and settles with Telegram's own ~3 % overshoot; normalised to end
  exactly on 1 at SETTLE s (residual there < 1e-4 of the move), so no rest frame differs from the cover.
  opacities: smoothstep (zero slope at both ends).
Motion blur: temporal supersampling over a 180-degree shutter, averaged in linear light; static dither.

Usage: render_a.py frames OUTDIR FPS SIZE SUB  |  render_a.py zones FPS  |  render_a.py cover OUT.png SIZE  |  render_a.py svg OUT.svg"""
import sys, math, os
import cairo, numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import svgpath

BG0, BG1, ARROW = '#2AABEE', '#229ED9', '#229ED9'
R, FW, FH, BW, BH = 36, 300, 210, 240, 210
PEEK, BACK_A = float(os.environ.get('PEEK', 52)), float(os.environ.get('BACK_A', 0.55))
def geom():
    top = (640 - (PEEK + FH)) / 2                       # glyph box centred vertically
    return (320 - FW/2, top + PEEK, FW, FH), (320 - BW/2, top, BW, BH)
ARROW_D = ('M16.403 6.394A1.422 1.422 0 0 1 18.79 5.35l10.395 9.606c.577.533.612 1.433.061 2.029l-.061.06-10.395 '
           '9.606a1.422 1.422 0 0 1-2.388-1.044v-4.398c-5.363.129-9.026 1.841-11.064 5.103l-.195.324a.969.969 0 0 '
           '1-1.808-.47c-.138-9.741 4.129-14.936 12.638-15.34l.429-.016V6.394z')
ARROW_OPS = svgpath.parse(ARROW_D)
A_S = 5.8
A_DX, A_DY = 224.387 - 170 - FW/2, 246.939 - 235 - FH/2   # arrow origin relative to the front card's centre

LOOP, T0 = 2.4, 0.6
EXIT_DUR, EXIT_DX = 0.66, 480
T_BACK, T_ARROW, T_NEXT = T0 + 0.13, T0 + 0.475, T0 + 0.46
SETTLE = 0.92
T_END = T_ARROW + SETTLE

def hexc(h): return tuple(int(h[i:i+2], 16)/255 for i in (1, 3, 5))
def bez(x, p1x=0.33, p1y=0.52, p2x=0.25, p2y=0.99):      # Telegram iOS slide curve y(x)
    if x <= 0: return 0.0
    if x >= 1: return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(50):
        t = (lo + hi) / 2
        bx = 3*(1-t)**2*t*p1x + 3*(1-t)*t**2*p2x + t**3
        lo, hi = (t, hi) if bx < x else (lo, t)
    t = (lo + hi) / 2
    return 3*(1-t)**2*t*p1y + 3*(1-t)*t**2*p2y + t**3
def ease_in(x): return 1 - bez(1 - x, 0.33, 0.52, 0.25, 1.0)
# ^ the slide curve mirrored (accelerating), with p2y 0.99 -> 1.0 so the exit starts at exactly zero speed
#   (with 0.99 it would start at 0.4 px/frame out of the rest)
M_, K_, C_ = 5.0, 900.0, 100.0
_W0 = math.sqrt(K_/M_); _Z = C_ / (2*math.sqrt(K_*M_)); _WD = _W0*math.sqrt(1 - _Z*_Z)
def _spring_raw(t):                                      # step response, x(0)=0, v(0)=0, underdamped
    return 1 - math.exp(-_Z*_W0*t) * (math.cos(_WD*t) + _Z*_W0/_WD*math.sin(_WD*t))
_SN = _spring_raw(SETTLE)
def spring(t):
    if t <= 0: return 0.0
    if t >= SETTLE: return 1.0
    return _spring_raw(t) / _SN
def smooth(x): x = min(max(x, 0.0), 1.0); return x*x*(3 - 2*x)
def win(t, a, b): return (t - a) / (b - a)
def lerp(a, b, t): return a + (b - a)*t

def rrect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x+w-r, y+r, r, -math.pi/2, 0); cr.arc(x+w-r, y+h-r, r, 0, math.pi/2)
    cr.arc(x+r, y+h-r, r, math.pi/2, math.pi); cr.arc(x+r, y+r, r, math.pi, 1.5*math.pi)
    cr.close_path()

def card(cr, rect, alpha, arrow=0.0, adx=0.0):
    x, y, w, h = rect
    if alpha <= 0: return
    cr.push_group()
    rrect(cr, x, y, w, h, R); cr.set_source_rgb(1, 1, 1); cr.fill()
    if arrow > 0:
        k = w / FW
        svgpath.draw(cr, ARROW_OPS, x + w/2 + A_DX*k + adx, y + h/2 + A_DY*k, A_S*k)
        cr.set_source_rgba(*hexc(ARROW), arrow); cr.fill()
    cr.pop_group_to_source(); cr.paint_with_alpha(alpha)

def state(t):
    """Every element's geometry and opacity at loop time t (seconds); t outside the motion = the cover."""
    FRONT, BACK = geom()
    t = t % LOOP
    if not (T0 < t < T_END): t = T0                     # rest: exactly the cover
    s = spring(t - T_NEXT)
    nb = ((BACK[0] + (1-s)*12, BACK[1] + (1-s)*PEEK, BACK[2] - (1-s)*24, BACK[3]),
          BACK_A*smooth(win(t, T_NEXT, T_NEXT + 0.66)), 0.0, 0.0)
    s = spring(t - T_BACK)
    mid = (tuple(lerp(a, b, s) for a, b in zip(BACK, FRONT)),
           lerp(BACK_A, 1.0, smooth(win(t, T0 + 0.37, T0 + 0.92))),
           smooth(win(t, T_ARROW, T_ARROW + 0.30)), -56*(1 - spring(t - T_ARROW)))
    e = ease_in(win(t, T0, T0 + EXIT_DUR))
    old = ((FRONT[0] + EXIT_DX*e, FRONT[1], FRONT[2], FRONT[3]), 1.0 if t < T0 + EXIT_DUR else 0.0, 1.0, 0.0)
    return [nb, mid, old]               # bottom to top; at t = T0 (the cover) the next back is invisible, mid = the back card

def draw(t, S):
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, S, S)
    cr = cairo.Context(surf); cr.scale(S/640, S/640)
    g = cairo.LinearGradient(0, 0, 0, 640)
    g.add_color_stop_rgb(0, *hexc(BG0)); g.add_color_stop_rgb(1, *hexc(BG1))
    cr.set_source(g); cr.paint()
    nb, mid, old = state(t)
    # the next back card is hidden wherever the card in front of it is, even while that card is still translucent
    # (seen through it, it read as a ghost card inside the card)
    cr.save(); cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD); cr.rectangle(-10, -10, 660, 660); rrect(cr, *mid[0], R); cr.clip()
    card(cr, *nb); cr.restore()
    card(cr, *mid); card(cr, *old)
    surf.flush()
    a = np.frombuffer(surf.get_data(), np.uint8).reshape(S, surf.get_stride()//4, 4)[:, :S, :3][:, :, ::-1]
    return a.astype(np.float64) / 255

def lin(x): return np.where(x <= 0.04045, x/12.92, ((x+0.055)/1.055)**2.4)
def srgb(x): return np.where(x <= 0.0031308, x*12.92, 1.055*np.power(np.maximum(x, 0), 1/2.4) - 0.055)
def dither(S): return (np.random.default_rng(7).random((S, S, 1)) - 0.5) / 255
def to8(img): return (np.clip(img, 0, 1)*255 + 0.5).astype(np.uint8)

def samples(i, FPS, SUB):                                   # 180-degree shutter centred on the frame time
    return [(i + (s + 0.5)/SUB*0.5 - 0.25)/FPS for s in range(SUB)]
def is_rest(i, FPS, SUB=64): return all(not (T0 < t % LOOP < T_END) for t in samples(i, FPS, SUB))
def rest_zones(FPS):
    """x264 --zones string giving every rest frame (exact cover) a near-lossless constant QP: frame 0 is the I-frame
    the loop starts on, the rest frames after the motion are coded once at that quality and then skipped, so the
    still part of the loop does not shimmer and the seam back to frame 0 is invisible."""
    N = round(FPS*LOOP); R_ = [i for i in range(N) if is_rest(i, FPS)]; runs = []
    for i in R_:
        if runs and runs[-1][1] == i - 1: runs[-1][1] = i
        else: runs.append([i, i])
    return '/'.join(f'{a},{b},q={QP_REST}' for a, b in runs)
QP_REST = 4

def svg():
    FRONT, BACK = geom()
    ax, ay = FRONT[0] + FW/2 + A_DX, FRONT[1] + FH/2 + A_DY
    f = lambda v: f'{v:.3f}'.rstrip('0').rstrip('.')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="640" height="640" viewBox="0 0 640 640">
<!-- Feed (@FeedChannelsBot) avatar, direction A «stack of posts»: the static avatar and the rest frame of the
     animated one (render_a.py). Telegram logo gradient #2AABEE -> #229ED9 (press-kit Logo.svg); back card 240 x 210
     at {BACK_A:g} opacity showing {PEEK:g} px above the front card 300 x 210, radius 36, glyph centred; forward arrow:
     Telegram Web A share-filled.svg (github.com/Ajaxy/telegram-tt, src/assets/font-icons), scale 5.8.
     Claude (Opus 5.5), 2026-11-18. -->
<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{BG0}"/><stop offset="1" stop-color="{BG1}"/></linearGradient></defs>
<rect width="640" height="640" fill="url(#bg)"/>
<rect x="{f(BACK[0])}" y="{f(BACK[1])}" width="{BW}" height="{BH}" rx="{R}" fill="#FFFFFF" fill-opacity="{BACK_A:g}"/>
<rect x="{f(FRONT[0])}" y="{f(FRONT[1])}" width="{FW}" height="{FH}" rx="{R}" fill="#FFFFFF"/>
<path transform="translate({f(ax)} {f(ay)}) scale({A_S:g})" fill="{ARROW}" d="{ARROW_D}"/>
</svg>
'''

if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'zones': print(rest_zones(int(sys.argv[2]))); sys.exit()
    if mode == 'svg': open(sys.argv[2], 'w').write(svg()); sys.exit()
    if mode == 'cover':
        S = int(sys.argv[3]); Image.fromarray(to8(draw(0.0, S) + dither(S))).save(sys.argv[2]); sys.exit()
    out, FPS, S, SUB = sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
    N = round(FPS*LOOP); os.makedirs(out, exist_ok=True); dt = dither(S)
    cover = to8(draw(0.0, S) + dt); rest = 0
    for i in range(N):
        ts = samples(i, FPS, SUB)
        if is_rest(i, FPS, SUB): img = cover; rest += 1
        else: img = to8(srgb(sum(lin(draw(t, S)) for t in ts)/SUB) + dt)
        Image.fromarray(img).save(f'{out}/{i:04d}.png')
    print(f'frames={N} at {FPS} fps, {SUB} samples; rest frames (exact cover) = {rest}; motion {T0}-{T_END:.3f} s')
