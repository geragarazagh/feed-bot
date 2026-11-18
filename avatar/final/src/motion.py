"""Motion audit of render_a.state() inside the motion window: speeds in px/frame at 800 px, 30 fps; the speed each
motion starts and ends with (0 = continuous with the rest); the largest acceleration (a kick shows as a spike);
circle-crop margins; overshoots; a speed plot."""
import sys, math, numpy as np
sys.path.insert(0, '.')
import render_a as r
from PIL import Image, ImageDraw
dt = 1/6000; T = np.arange(r.T0 + 1e-9, r.T_END - 1e-9, dt)
U = 800/640/30                                       # 640-units per second -> px per frame at 800, 30 fps
names = ['next back', 'back->front', 'old front']
P = {n: np.array([(*st[0], st[1], st[2], st[3]) for st in [r.state(t)[k] for t in T]]) for k, n in enumerate(names)}
FRONT, BACK = r.geom()
def report(n, cols, label):
    A = P[n]; X = A[:, cols]                         # tracked coordinate(s)
    V = np.gradient(X, dt, axis=0) * U               # px/frame
    Acc = np.gradient(V, dt, axis=0) / 30            # px/frame per frame
    sp = np.abs(V); vis = A[:, 4] > 0
    print(f'{label:26s} start speed {sp[0]:.3f}  end speed {sp[vis][-1]:.3f}  peak {sp.max():.1f} px/frame; '
          f'peak accel {np.abs(Acc[vis]).max():.2f} px/frame2')
report('old front', 0, 'old front x')
report('back->front', 1, 'back->front y')
report('back->front', 2, 'back->front width')
X = P['back->front'][:, 0] + P['back->front'][:, 2]/2 + P['back->front'][:, 6]
V = np.gradient(X, dt)*U; print(f'{"arrow x (on new front)":26s} start speed {abs(V[0]):.3f}  end {abs(V[-1]):.3f}  peak {np.abs(V).max():.1f} px/frame')
report('next back', 1, 'next back y')
for n, k in (('next back', 4), ('back->front', 4), ('back->front', 5)):
    a = P[n][:, k]; va = np.gradient(a, dt)
    print(f'opacity {n} {"arrow" if k == 5 else "card"}: start slope {abs(va[0]):.4f}/s, end slope {abs(va[-1]):.4f}/s, max {np.abs(va).max():.2f}/s')
for n in ('next back', 'back->front'):
    A = P[n]; m = min(320 - (max(math.hypot(cx - 320, cy - 320) for cx in (x + r.R, x + w - r.R) for cy in (y + r.R, y + h - r.R)) + r.R)
                     for x, y, w, h, *_ in A[::20])
    print(f'{n}: closest approach to the round crop {m:.1f} units (positive = inside)')
A = P['old front']; vis = A[:, 4] > 0
print(f'old front: left edge when it disappears {A[vis][-1][0]:.1f} (frame edge 640)')
print(f'overshoots (units at 640): back->front y {P["back->front"][:,1].max()-FRONT[1]:.2f}, width {P["back->front"][:,2].max()-FW if (FW:=FRONT[2]) else 0:.2f}, '
      f'arrow {X.max()-(FRONT[0]+150):.2f}, next back y {BACK[1]-P["next back"][:,1].min():.2f}')
print(f'spring zeta {r._Z:.3f} w0 {r._W0:.2f}; normalised at {r.SETTLE}s, raw residual {abs(1-r._spring_raw(r.SETTLE)):.1e}; motion {r.T0}-{r.T_END:.3f}s')
# plot: speed of each object over the loop
W, H = 1200, 300; im = Image.new('RGB', (W, H), 'white'); d = ImageDraw.Draw(im)
def plot(xs, col):
    pts = [(int(t/r.LOOP*W), int(H - 20 - min(v, 50)/50*(H - 40))) for t, v in zip(T[::20], xs[::20])]; d.line(pts, fill=col, width=2)
plot(np.abs(np.gradient(P['old front'][:, 0], dt)*U)*(P['old front'][:, 4] > 0), (200, 60, 60))
B = P['back->front']; plot(np.hypot(np.gradient(B[:, 0] + B[:, 2]/2, dt), np.gradient(B[:, 1], dt))*U, (34, 158, 217))
plot(np.abs(V), (120, 60, 200)); plot(np.abs(np.gradient(P['next back'][:, 1], dt))*U, (0, 150, 0))
for k in range(25): d.line((k*W/24, H - 20, k*W/24, H - 12), fill='black')
im.save('fin/speed.png')
