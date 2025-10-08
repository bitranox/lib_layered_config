{
  description = "Cross-platform layered configuration loader for Python";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.05";
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        lib = pkgs.lib;
        pypkgs = pkgs.python313Packages;

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
        libCliExitToolsVendor = pypkgs.buildPythonPackage rec {
          pname = "lib_cli_exit_tools";
          version = "1.6.0";
          format = "wheel";
          src = pkgs.fetchurl {
            url = "https://files.pythonhosted.org/packages/7a/ce/e4999128794f53702abde5d245a316bc552e0d5cbdffc75a650189a3b0a1/lib_cli_exit_tools-1.6.0-py3-none-any.whl";
            sha256 = "sha256-vz7E/xEX7wg+OvLr5EBDs2ZKWCvP7ZoaUvgfajTWP3M=";
          };
          doCheck = false;
        };

        richClickVendor = pypkgs.buildPythonPackage rec {
          pname = "rich-click";
          version = "1.9.2";
          format = "wheel";
          src = pkgs.fetchurl {
            url = "https://files.pythonhosted.org/packages/a9/27/7a82106d69738aefb81e044d6dd278053c5263581c5e8e5330e1339b8444/rich_click-1.9.2-py3-none-any.whl";
            sha256 = "sha256-UHna1n7X30NKnsHyCx1i2DHljHh0ACb5aM49O4YfAaA=";
          };
          doCheck = false;
        };

      in
      {
        packages.default = pypkgs.buildPythonPackage {
          pname = "lib_layered_config";
          version = "0.1.1";
          pyproject = true;
          src = ../..;
          nativeBuildInputs = [ hatchlingVendor ];
          propagatedBuildInputs = [ libCliExitToolsVendor richClickVendor ];

          meta = with pkgs.lib; {
            description = "Cross-platform layered configuration loader for Python";
            homepage = "https://github.com/bitranox/lib_layered_config";
            license = licenses.mit;
            maintainers = [];
            platforms = platforms.unix ++ platforms.darwin;
          };
        };

        devShells.default = pkgs.mkShell {
          packages = [
            pkgs.python313
            hatchlingVendor
            libCliExitToolsVendor
            richClickVendor
            pypkgs.pytest
            pkgs.ruff
            pkgs.nodejs
          ];
        };
      }
    );
}
