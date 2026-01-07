{
  description = "autocodegen - Library and utilities for auto-code generators";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    uv2nix.url = "github:adisbladis/uv2nix?ref=main";
  };

  outputs = {
    self,
    nixpkgs,
    flake-utils,
    uv2nix,
  }:
    flake-utils.lib.eachDefaultSystem (system: let
      pkgs = import nixpkgs {inherit system;};

      uv = uv2nix.lib.mkUv2Nix {
        projectRoot = self;
      };

      # Build Python environment from uv.lock + pyproject.toml
      pythonEnv = uv.mkPythonEnv {
        inherit pkgs;
      };
    in {
      packages.default = pythonEnv;

      apps.default = {
        type = "app";
        program = "${pythonEnv}/bin/acg";
      };
    });
}
