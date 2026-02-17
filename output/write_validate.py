import pathlib, sys
data = pathlib.Path(sys.argv[1]).read_bytes()
out = pathlib.Path(sys.argv[2])
out.write_bytes(data)
print(f"Copied {len(data)} bytes to {out}")
