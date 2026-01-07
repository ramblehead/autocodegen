{
  description = "autocodegen - Library and utilities for auto-code generators";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    uv2nix.url = "github:adisbladis/uv2nix";
  };

  outputs = {
    self,
    nixpkgs,
    flake-utils,
    uv2nix,
  }:
    flake-utils.lib.eachDefaultSystem (system: let
      pkgs = import nixpkgs {inherit system;};

      uv = uv2nix.lib {
        inherit pkgs;
        projectRoot = self;
      };

      pythonEnv = uv.mkPythonEnv {};
    in {
      packages.default = pythonEnv;

      # Expose the correct script name for `nix run`
      apps.default = {
        type = "app";
        program = "${pythonEnv}/bin/acg";
      };
    });
}
