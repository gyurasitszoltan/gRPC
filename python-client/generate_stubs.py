import importlib
from pathlib import Path


def main() -> int:
    protoc = importlib.import_module("grpc_tools.protoc")
    project_root = Path(__file__).resolve().parent.parent
    proto_file = project_root / "proto" / "demo.proto"
    output_dir = Path(__file__).resolve().parent / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "__init__.py").touch(exist_ok=True)

    result = protoc.main(
        [
            "grpc_tools.protoc",
            f"-I{proto_file.parent}",
            f"--python_out={output_dir}",
            f"--grpc_python_out={output_dir}",
            str(proto_file),
        ]
    )

    if result != 0:
        print("Stub generalas sikertelen.")
        return result

    print(f"Stubok generalva: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
