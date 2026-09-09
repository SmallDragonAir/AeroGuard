from pathlib import Path

root = Path(r"D:\MSFS2024_DATA\Community\fsl-a32x")

path = root / r"SimObjects\Airplanes\FSLabs A321-NEO LEAP CCA B-32CD"

print("is_dir:", path.is_dir())
print("is_symlink:", path.is_symlink())
print("is_junction:", path.is_junction())
print("readlink:", path.readlink())
print("resolve:", path.resolve())