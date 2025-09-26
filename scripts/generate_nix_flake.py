from __future__ import annotations

import textwrap
from pathlib import Path
from string import Template
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from scripts._utils import read_version_from_pyproject
from scripts.bump_version import (
    PROJECT_META,
    _min_py_from_requires,
    _preferred_dependency_version,
    _pypi_wheel_info,
    _read_pyproject_deps,
    _read_requires_python,
)


def _vendor_identifier(name: str, existing: set[str]) -> str:
    parts = re.split(r"[^0-9A-Za-z]+", name)
    parts = [p for p in parts if p]
    if not parts:
        base = name.replace("-", "_")
    else:
        base = parts[0].lower() + "".join(p.capitalize() for p in parts[1:])
    candidate = base + "Vendor"
    while candidate in existing:
        candidate += "X"
    existing.add(candidate)
    return candidate


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def generate_flake(version: str) -> str:
    deps = _read_pyproject_deps(Path("pyproject.toml"))
    req = _read_requires_python(Path("pyproject.toml"))
    min_py = _min_py_from_requires(req or "") if req else None
    python_digits = (min_py or "3.10").replace(".", "")

    vendor_infos = []
    seen_idents: set[str] = set()
    for dep_name in sorted(deps.keys()):
        spec = deps[dep_name]
        desired_version = _preferred_dependency_version(dep_name, spec)
        if not desired_version:
            continue
        wheel_url, nix_hash = _pypi_wheel_info(dep_name, desired_version)
        if not wheel_url or not nix_hash:
            continue
        ident = _vendor_identifier(dep_name, seen_idents)
        vendor_infos.append(
            {
                "ident": ident,
                "pname": dep_name,
                "version": desired_version,
                "url": wheel_url,
                "hash": nix_hash,
            }
        )

    if not vendor_infos:
        raise SystemExit("no vendorable dependencies detected")

    vendor_blocks = "\n".join(
        textwrap.indent(
            textwrap.dedent(
                """{ident} = pypkgs.buildPythonPackage rec {{
  pname = "{pname}";
  version = "{version}";
  format = "wheel";
  src = pkgs.fetchurl {{
    url = "{url}";
    sha256 = "{hash}";
  }};
  doCheck = false;
}};
"""
            ).format(**info),
            "        ",
        )
        for info in vendor_infos
    )

    prop_inputs = " ".join(info["ident"] for info in vendor_infos)
    devshell_nodes = (
        [f"pkgs.python{python_digits}", "hatchlingVendor"]
        + [info["ident"] for info in vendor_infos]
        + ["pypkgs.pytest", "pkgs.ruff", "pkgs.nodejs"]
    )
    devshell_inputs = "\n".join(f"            {item}" for item in _ordered_unique(devshell_nodes))

    template = Template(
        textwrap.dedent(
            """{
  description = "bitranox_template_py_cli Nix flake";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.05";
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        lib = pkgs.lib;
        pypkgs = pkgs.python${digits}Packages;

        hatchlingVendor = pypkgs.buildPythonPackage rec {
          pname = "hatchling";
          version = "1.25.0";
          format = "wheel";
          src = pkgs.fetchurl {
            url = "https://files.pythonhosted.org/packages/py3/h/hatchling/hatchling-1.25.0-py3-none-any.whl";
            hash = "sha256-tHlI5F1NlzA0WE3UyznBS2pwInzyh6t+wK15g0CKiCw";
          };
          propagatedBuildInputs = [
            pypkgs.packaging
            pypkgs.tomli
            pypkgs.pathspec
            pypkgs.pluggy
            pypkgs."trove-classifiers"
            pypkgs.editables
          ];
          doCheck = false;
        };
${vendor_blocks}
      in
      {
        packages.default = pypkgs.buildPythonPackage {
          pname = "${pname}";
          version = "${version}";
          pyproject = true;
          src = ../..;
          nativeBuildInputs = [ hatchlingVendor ];
          propagatedBuildInputs = [ ${prop_inputs} ];

          meta = with pkgs.lib; {
            description = "Rich-powered logging helpers for colorful terminal output";
            homepage = "https://github.com/bitranox/bitranox_template_py_cli";
            license = licenses.mit;
            maintainers = [];
            platforms = platforms.unix ++ platforms.darwin;
          };
        };

        devShells.default = pkgs.mkShell {
          packages = [
${devshell_inputs}
          ];
        };
      }
    );
}
"""
        )
    )

    return template.substitute(
        digits=python_digits,
        vendor_blocks=vendor_blocks,
        pname=PROJECT_META.name,
        version=version,
        prop_inputs=prop_inputs,
        devshell_inputs=devshell_inputs,
    )


def main() -> None:
    version = read_version_from_pyproject()
    if not version:
        raise SystemExit("version not found in pyproject.toml")

    flake_text = generate_flake(version)
    Path("packaging/nix/flake.nix").write_text(flake_text, encoding="utf-8")
    print("[nix] Flake regenerated with vendored dependencies")


if __name__ == "__main__":
    main()
