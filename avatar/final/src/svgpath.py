"""Minimal SVG path data -> cairo: M m L l H h V v C c A a Z z (all this avatar's arrow uses).
Arcs become cubic Beziers (endpoint -> centre parametrisation, SVG 1.1 implementation notes F.6.5)."""
import math, re

def _tokens(d):
    for t in re.findall(r'[MmLlHhVvCcAaZz]|-?(?:\d+\.?\d*|\.\d+)(?:e-?\d+)?', d):
        yield t

def parse(d):
    """Returns a list of absolute ops: ('M',x,y) ('L',x,y) ('C',x1,y1,x2,y2,x,y) ('Z',)."""
    toks = list(_tokens(d)); i = 0; out = []; cx = cy = sx = sy = 0.0; cmd = None
    def num():
        nonlocal i; v = float(toks[i]); i += 1; return v
    while i < len(toks):
        if re.fullmatch(r'[A-Za-z]', toks[i]): cmd = toks[i]; i += 1
        rel = cmd.islower(); C = cmd.upper()
        if C == 'Z':
            out.append(('Z',)); cx, cy = sx, sy; continue
        if C == 'M':
            x, y = num(), num()
            if rel: x += cx; y += cy
            out.append(('M', x, y)); cx, cy = sx, sy = x, y; cmd = 'l' if rel else 'L'; continue
        if C == 'L':
            x, y = num(), num()
            if rel: x += cx; y += cy
            out.append(('L', x, y)); cx, cy = x, y; continue
        if C == 'H':
            x = num() + (cx if rel else 0); out.append(('L', x, cy)); cx = x; continue
        if C == 'V':
            y = num() + (cy if rel else 0); out.append(('L', cx, y)); cy = y; continue
        if C == 'C':
            p = [num() for _ in range(6)]
            if rel: p = [v + (cx if k % 2 == 0 else cy) for k, v in enumerate(p)]
            out.append(('C', *p)); cx, cy = p[4], p[5]; continue
        if C == 'A':
            rx, ry, phi, fa, fs, x, y = num(), num(), num(), num(), num(), num(), num()
            if rel: x += cx; y += cy
            out += _arc(cx, cy, rx, ry, phi, int(fa), int(fs), x, y); cx, cy = x, y; continue
        raise ValueError(cmd)
    return out

def _arc(x1, y1, rx, ry, phi, fa, fs, x2, y2):
    if rx == 0 or ry == 0: return [('L', x2, y2)]
    p = math.radians(phi); cp, sp = math.cos(p), math.sin(p)
    dx, dy = (x1 - x2)/2, (y1 - y2)/2
    x1p, y1p = cp*dx + sp*dy, -sp*dx + cp*dy
    rx, ry = abs(rx), abs(ry)
    lam = x1p**2/rx**2 + y1p**2/ry**2
    if lam > 1: rx *= math.sqrt(lam); ry *= math.sqrt(lam)
    num = rx*rx*ry*ry - rx*rx*y1p*y1p - ry*ry*x1p*x1p
    den = rx*rx*y1p*y1p + ry*ry*x1p*x1p
    co = math.sqrt(max(0.0, num/den)) * (-1 if fa == fs else 1)
    cxp, cyp = co*rx*y1p/ry, -co*ry*x1p/rx
    cx, cy = cp*cxp - sp*cyp + (x1 + x2)/2, sp*cxp + cp*cyp + (y1 + y2)/2
    def ang(ux, uy, vx, vy):
        a = math.atan2(ux*vy - uy*vx, ux*vx + uy*vy); return a
    t1 = ang(1, 0, (x1p - cxp)/rx, (y1p - cyp)/ry)
    dt = ang((x1p - cxp)/rx, (y1p - cyp)/ry, (-x1p - cxp)/rx, (-y1p - cyp)/ry)
    if not fs and dt > 0: dt -= 2*math.pi
    if fs and dt < 0: dt += 2*math.pi
    n = max(1, math.ceil(abs(dt)/(math.pi/2))); d = dt/n; k = 4/3*math.tan(d/4); out = []
    def pt(t): return (cx + rx*math.cos(t)*cp - ry*math.sin(t)*sp, cy + rx*math.cos(t)*sp + ry*math.sin(t)*cp)
    def dv(t): return (-rx*math.sin(t)*cp - ry*math.cos(t)*sp, -rx*math.sin(t)*sp + ry*math.cos(t)*cp)
    t = t1
    for _ in range(n):
        a0, a1 = pt(t), pt(t + d); d0, d1 = dv(t), dv(t + d)
        out.append(('C', a0[0] + k*d0[0], a0[1] + k*d0[1], a1[0] - k*d1[0], a1[1] - k*d1[1], a1[0], a1[1])); t += d
    return out

def draw(cr, ops, tx=0.0, ty=0.0, s=1.0):
    for op in ops:
        if op[0] == 'M': cr.move_to(tx + s*op[1], ty + s*op[2])
        elif op[0] == 'L': cr.line_to(tx + s*op[1], ty + s*op[2])
        elif op[0] == 'C': cr.curve_to(*[(tx if k % 2 == 0 else ty) + s*v for k, v in enumerate(op[1:])])
        else: cr.close_path()
