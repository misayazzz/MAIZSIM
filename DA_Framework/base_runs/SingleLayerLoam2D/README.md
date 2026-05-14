# SingleLayerLoam2D base run

This is a self-contained first-stage MAIZSIM/2DSOIL base run for the DA framework. It uses WYE07 crop/weather/management inputs generated in a temporary workspace from the repository Excel input tool, then replaces the soil with one homogeneous loam material.

Key choices:

- `run.dat` uses relative paths so copied ensemble member directories remain self-contained.
- `LOAM2D.grd` has `NumMat = 1`; all node and element material IDs are `1`.
- `Loam_200cm.soi` has one material row with `thetaS = 0.430` and `n = 1.560`, matching the first IES defaults.
- The validation window is `2007-04-28` through `2007-07-04`, covering ten 5-day observation windows from `2007-05-20` through `2007-07-04`.

Run from this directory with:

```powershell
.\2dMAIZSIM.exe .\run.dat
```
