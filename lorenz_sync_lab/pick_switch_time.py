"""
Find a switch-on time near 6 where each row's single run shows that
controller's TYPICAL outcome (per ensemble_lorenz_sync.py):

    xweak  no lock      (locks in 0.5% of starts)
    x      lock         (100%)
    z      no lock      (25%)
    xz     lock         (56%)
    xy     lock         (85%)

The scene shows one run per row, so this choice is disclosed in its README.
"""
import numpy as np

import generate_lorenz_sync as gen

WANT = {"xweak": False, "x": True, "z": False, "xz": True, "xy": True}
TAIL = int(round(2.0 / gen.DT))

for t_on in np.round(np.arange(5.0, 7.01, 0.1), 2):
    gen.T_ON = float(t_on)
    gen.F_ON = int(round(t_on / gen.FRAME_DT))
    _, runs = gen.simulate()
    got, lock_t = {}, {}
    for key, fine in runs.items():
        err = np.linalg.norm(fine[:, :3] - fine[:, 3:], axis=1)
        got[key] = bool(err[-TAIL:].max() < 0.1)
        far = np.where(err[::gen.SUBSTEPS] >= 0.1)[0]
        lock_t[key] = round((far[-1] + 1) * gen.FRAME_DT, 2) if got[key] else None
    ok = got == WANT
    print(f"T_ON={t_on:4.1f}  {'MATCH' if ok else '     '}  "
          + "  ".join(f"{k}:{'L' if v else '-'}{'' if lock_t[k] is None else '@' + str(lock_t[k])}"
                      for k, v in got.items()))
