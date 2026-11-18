"""Audit of the encoded loop. Usage: audit.py FRAMEDIR MP4 FPS [TAG]
seam SSIM, rest-frame jitter after decoding, colour error, gradient banding, white-edge chroma error; a Telegram-like
480 re-encode (H.264 Main, CRF 23) checked the same way; pictures for the eye in fin/audit_<TAG>_*.png."""
import sys, glob, subprocess, numpy as np
from PIL import Image
sys.path.insert(0, '.')
import render_a as r

def ssim(a, b):
    a = a.astype(np.float64); b = b.astype(np.float64)
    def box(x):
        c = np.pad(x, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
        return (c[7:, 7:] - c[:-7, 7:] - c[7:, :-7] + c[:-7, :-7]) / 49
    ma, mb = box(a), box(b)
    va = (box(a*a) - ma**2)*49/48; vb = (box(b*b) - mb**2)*49/48; cv = (box(a*b) - ma*mb)*49/48
    C1, C2 = (0.01*255)**2, (0.03*255)**2
    return float((((2*ma*mb + C1)*(2*cv + C2))/((ma**2 + mb**2 + C1)*(va + vb + C2)))[3:-3, 3:-3].mean())
def gray(a): return (a[..., 0]*0.299 + a[..., 1]*0.587 + a[..., 2]*0.114)
def decode(path, S):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, S, S, 3).astype(int)

fd, mp4, FPS = sys.argv[1], sys.argv[2], int(sys.argv[3]); tag = sys.argv[4] if len(sys.argv) > 4 else 'x'
src = np.stack([np.asarray(Image.open(f).convert('RGB')).astype(int) for f in sorted(glob.glob(fd + '/*.png'))])
N, S = len(src), src.shape[1]
dec = decode(mp4, S)
rest = [i for i in range(N) if r.is_rest(i, FPS)]
g = [gray(f) for f in dec]
adj = [ssim(g[i], g[i+1]) for i in range(N - 1)]
print(f'{mp4.split("/")[-1]}: frames {len(dec)}, seam SSIM last->first {ssim(g[-1], g[0]):.4f}, lowest adjacent {min(adj):.4f}')
print(f'  source rest frames identical to frame 0: {all((src[i] == src[0]).all() for i in rest)} ({len(rest)} frames)')
print(f'  decoded rest frames vs decoded frame 0: max |diff| {max(np.abs(dec[i] - dec[0]).max() for i in rest)} (0-255)')
e = np.abs(dec[0] - src[0])
FRONT, BACK = r.geom(); k = S/640
x0, y0, x1, y1 = [int(round(v*k)) for v in (FRONT[0], FRONT[1], FRONT[0] + FRONT[2], FRONT[1] + FRONT[3])]
edge = np.zeros((S, S), bool); edge[y0-3:y1+3, x0-3:x1+3] = True; edge[y0+4:y1-4, x0+4:x1-4] = False
print(f'  cover decoded vs source: mean {e.mean():.2f}, max {e.max()}, 99.9th pct {np.percentile(e, 99.9):.0f}; '
      f'at the white card edge (±3 px): mean {e[edge].mean():.2f}, max {e[edge].max()}')
col = src[0][:, 40, :]; dcol = dec[0][:, 40, :]
print(f'  gradient column x=40: largest step source {np.abs(np.diff(col, axis=0)).max()}, decoded {np.abs(np.diff(dcol, axis=0)).max()} '
      f'(1 = one 8-bit level, invisible)')
# Telegram-like re-encode at 480, Main profile
t480 = f'fin/tg480_{tag}.mp4'
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', mp4, '-vf', 'scale=480:480:flags=bicubic', '-c:v', 'libx264', '-profile:v', 'main',
                '-preset', 'medium', '-crf', '23', '-pix_fmt', 'yuv420p', '-an', t480], check=True)
d4 = decode(t480, 480)
ref = np.stack([np.asarray(Image.fromarray(f.astype(np.uint8)).resize((480, 480), Image.BICUBIC)).astype(int) for f in src])
e4 = np.abs(d4 - ref); g4 = [gray(f) for f in d4]
mse = ((d4 - ref)**2).mean(); psnr = 10*np.log10(255**2/mse)
print(f'  480 Main CRF 23 re-encode: {__import__("os").path.getsize(t480)} bytes, PSNR {psnr:.1f} dB vs source, '
      f'seam SSIM {ssim(g4[-1], g4[0]):.4f}, worst frame mean error {e4.reshape(N, -1).mean(1).max():.2f}, '
      f'rest jitter max {max(np.abs(d4[i] - d4[0]).max() for i in rest)}')
# pictures: 4x crops of the front card's top-left corner (800 decoded, 480 re-encode), and the gradient stretched x16
def crop(a, box, z): return Image.fromarray(a[box[1]:box[3], box[0]:box[2]].astype(np.uint8)).resize(((box[2]-box[0])*z, (box[3]-box[1])*z), Image.NEAREST)
cx, cy = int(FRONT[0]*k), int(BACK[1]*k)
c8 = crop(dec[0], (cx - 10, cy - 10, cx + 70, cy + 110), 4); s8 = crop(src[0], (cx - 10, cy - 10, cx + 70, cy + 110), 4)
k4 = 480/640; cx4, cy4 = int(FRONT[0]*k4), int(BACK[1]*k4)
c4 = crop(d4[0], (cx4 - 6, cy4 - 6, cx4 + 42, cy4 + 66), 6)
sheet = Image.new('RGB', (s8.width*2 + c4.width + 40, max(s8.height, c4.height)), 'white')
sheet.paste(s8, (0, 0)); sheet.paste(c8, (s8.width + 20, 0)); sheet.paste(c4, (2*s8.width + 40, 0)); sheet.save(f'fin/audit_{tag}_edges.png')
st = np.clip((dec[0][:, :120].astype(float) - dec[0][:, :120].min(axis=(0, 1)))*16, 0, 255)
st4 = np.clip((d4[0][:, :72].astype(float) - d4[0][:, :72].min(axis=(0, 1)))*16, 0, 255)
b = Image.new('RGB', (120 + 20 + 72, S), 'white'); b.paste(Image.fromarray(st.astype(np.uint8)), (0, 0)); b.paste(Image.fromarray(st4.astype(np.uint8)), (140, 0))
b.save(f'fin/audit_{tag}_bands.png')
