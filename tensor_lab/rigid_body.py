"""
Torque-free rigid-body rotation: the physics behind Scene 3.

The book is a uniform box (mass 1) with half-dimensions H. In its own
principal basis its inertia tensor is diagonal,

    I_body = diag(I1, I2, I3),   I1 = (h2^2 + h3^2)/3, and cyclically,

and with no torque the angular momentum L is constant IN THE ROOM. In the
body's basis that same fact is Euler's equation,

    I dw/dt = (I w) x w        (w = angular velocity, body components)

and the orientation R (body -> room) follows dR/dt = R [w]x. Both are
integrated together with classical RK4 on (quaternion, w); the quaternion is
renormalized every step. verify_tensor_lab.py checks that L_room and the
kinetic energy hold to ~1e-10 over the run.
"""
import numpy as np

H = np.array([1.2, 0.75, 0.18])                 # half-dimensions: long, middle, thin
I_BODY = np.array([(H[1] ** 2 + H[2] ** 2) / 3,
                   (H[0] ** 2 + H[2] ** 2) / 3,
                   (H[0] ** 2 + H[1] ** 2) / 3])


def quat_mul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
                     w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                     w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def quat_to_matrix(q):
    w, x, y, z = q / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def matrix_to_quat(R):
    w = np.sqrt(max(0.0, 1 + R[0, 0] + R[1, 1] + R[2, 2])) / 2
    x = np.copysign(np.sqrt(max(0.0, 1 + R[0, 0] - R[1, 1] - R[2, 2])) / 2, R[2, 1] - R[1, 2])
    y = np.copysign(np.sqrt(max(0.0, 1 - R[0, 0] + R[1, 1] - R[2, 2])) / 2, R[0, 2] - R[2, 0])
    z = np.copysign(np.sqrt(max(0.0, 1 - R[0, 0] - R[1, 1] + R[2, 2])) / 2, R[1, 0] - R[0, 1])
    q = np.array([w, x, y, z])
    return q / np.linalg.norm(q)


def rhs(q, w, I=I_BODY):
    """(dq/dt, dw/dt) for body-frame w."""
    dw = np.cross(I * w, w) / I
    dq = 0.5 * quat_mul(q, np.array([0.0, *w]))
    return dq, dw


def integrate(R0, w0, dt, steps, sub=10, I=I_BODY):
    """Orientation and body-frame angular velocity at every step (steps + 1
    samples), integrated with `sub` RK4 substeps per step."""
    q = matrix_to_quat(R0)
    w = np.asarray(w0, float).copy()
    h = dt / sub
    Rs = np.empty((steps + 1, 3, 3))
    ws = np.empty((steps + 1, 3))
    Rs[0], ws[0] = quat_to_matrix(q), w
    for k in range(steps):
        for _ in range(sub):
            k1q, k1w = rhs(q, w, I)
            k2q, k2w = rhs(q + h / 2 * k1q, w + h / 2 * k1w, I)
            k3q, k3w = rhs(q + h / 2 * k2q, w + h / 2 * k2w, I)
            k4q, k4w = rhs(q + h * k3q, w + h * k3w, I)
            q = q + h / 6 * (k1q + 2 * k2q + 2 * k3q + k4q)
            w = w + h / 6 * (k1w + 2 * k2w + 2 * k3w + k4w)
            q = q / np.linalg.norm(q)
        Rs[k + 1], ws[k + 1] = quat_to_matrix(q), w
    return Rs, ws


def align_to_z(v):
    """A rotation taking the direction of v to +z (the shortest one)."""
    a = np.asarray(v, float) / np.linalg.norm(v)
    z = np.array([0.0, 0.0, 1.0])
    c = float(np.dot(a, z))
    if c > 1 - 1e-12:
        return np.eye(3)
    if c < -1 + 1e-12:
        return np.diag([1.0, -1.0, -1.0])
    k = np.cross(a, z)
    s = np.linalg.norm(k)
    k = k / s
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + s * K + (1 - c) * K @ K


def polhode(L0, I=I_BODY, dt=0.002, max_steps=200000):
    """One closed curve of the body-frame L (unit length) through L0:
    dL/dt = L x (I^-1 L). Integrates until the path returns to L0."""
    L = np.asarray(L0, float) / np.linalg.norm(L0)
    pts = [L.copy()]
    f = lambda v: np.cross(v, v / I)          # noqa: E731
    left = False
    for _ in range(max_steps):
        k1 = f(L)
        k2 = f(L + dt / 2 * k1)
        k3 = f(L + dt / 2 * k2)
        k4 = f(L + dt * k3)
        L = L + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        L /= np.linalg.norm(L)
        d = np.linalg.norm(L - pts[0])
        if d > 0.05:
            left = True
        if left and d < 0.01:
            pts.append(pts[0].copy())
            return np.array(pts)
        pts.append(L.copy())
    raise RuntimeError("polhode did not close")


def separatrix_normals(I=I_BODY):
    """The separatrix is two great circles through +/-e2: the planes
    L1 sqrt(1/I1 - 1/I2) = +/- L3 sqrt(1/I2 - 1/I3). -> their unit normals."""
    a = np.sqrt(1 / I[0] - 1 / I[1])
    c = np.sqrt(1 / I[1] - 1 / I[2])
    out = []
    for sgn in (1, -1):
        n = np.array([a, 0.0, -sgn * c])
        out.append(n / np.linalg.norm(n))
    return out
