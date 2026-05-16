
Maizsim has to be run from the command line. In the current Python/TOML workflow, `pixi run filecheat` creates a self-contained run folder. The Excel macro first writes a `run<ID>.dat` file, then Python renames it to `run.dat`, copies `2dMAIZSIM.exe`, `Maizsim.dll`, and `WaterBound.DAT` into the run folder, and rewrites the `WaterBound.DAT` reference inside `run.dat`.

## Windows build with VS C++ and Intel ifx

Build the solution through MSBuild. The solution uses a MSBuild-compatible makefile project for the Fortran executable instead of the legacy `.vfproj` file:

```powershell
MSBuild.exe .\maizsim07.sln /p:Configuration=Release /p:Platform=x64
```

The MSBuild project auto-detects Visual Studio C++ tools and Intel oneAPI from common `C:\` and `F:\` install locations, builds the C++ crop DLL with `cl/link`, then builds the Fortran soil executable with `ifx`.

Default build outputs are kept outside the source folders:

```text
build\maizsim\x64\Release\2dMAIZSIM.exe
build\maizsim\x64\Release\Maizsim.dll
```

Intermediate files, including the link-time `Maizsim.lib`, are written under `build\obj\...`.

From a generated run folder, run the model as:

```powershell
.\2dMAIZSIM.exe .\run.dat
```

The `run.dat` file contains paths and filenames of the input files:

D:\MAIZSIM07\MDEasternShore\Del06\DEL06.wea

D:\MAIZSIM07\MDEasternShore\Del06\DEL06.tim

D:\MAIZSIM07\MDEasternShore\Del06\BiologyDefault.bio

D:\MAIZSIM07\MDEasternShore\Del06\WyeClimate.dat

D:\MAIZSIM07\MDEasternShore\Del06\Del.nit

D:\MAIZSIM07\MDEasternShore\Del06\NitrogenDefault.sol

D:\MAIZSIM07\MDEasternShore\Del06\WyeSoil.soi

.

.

.

Older Excel-only examples may show names such as `runDEL06.dat` and may run the executable from a shared root folder. That is the legacy pattern. In the current automated workflow, use the generated `run.dat` in the run folder. `WaterBound.DAT` must still be present because the model opens it, even when the contents are not used unless the water boundary code requires time-dependent boundary conditions.


There are 5 output files:

DEL06.g01  -- plant output

DEL06.g02  --detaile leaf output

DEL06.G03  --water, temperature, concentration values at the nodes of the soil grid

DEL06.G04  --root information for the nodes or elements

DEL06.G05  -- surface fluxes, et, rain, transpiration

DEL06.G06  bottom and top boundary fluxes


The current automated workflow keeps each selected run self-contained. One can still put files in other folders because the full file paths are specified in `run.dat`, but the recommended generated layout keeps the executable, DLL, boundary file, grid files, soil file, and run file in the same run folder.
