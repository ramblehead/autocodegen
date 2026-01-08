{
  description = "autocodegen - Library and utilities for auto-code generators";

  inputs = {
    # e.g. flake-utils.lib.eachDefaultSystem (system: ...)
    flake-utils.url = "github:numtide/flake-utils";

    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = {
    flake-utils,
    nixpkgs,
    uv2nix,
    pyproject-nix,
    pyproject-build-systems,
    ...
  }:
    flake-utils.lib.eachDefaultSystem (
      system: let
        overlays = [
          (final: prev: {
            python = prev.python314;
            nodejs = prev.nodejs_24;
          })
        ];

        pkgs = import nixpkgs {inherit overlays system;};

        # Load a uv workspace from a workspace root.
        # Uv2nix treats all uv projects as workspace projects.
        workspace = uv2nix.lib.workspace.loadWorkspace {workspaceRoot = ./.;};

        # Create package overlay from workspace.
        overlay = workspace.mkPyprojectOverlay {
          # Prefer prebuilt binary wheels as a package source.  Sdists are less
          # likely to "just work" because of the metadata missing from uv.lock.
          # Binary wheels are more likely to, but may still require overrides for
          # library dependencies.
          sourcePreference = "wheel"; # or sourcePreference = "sdist";
          # Optionally customise PEP 508 environment
          # environ = {
          #   platform_release = "5.10.65";
          # };
        };

        # Extend generated overlay with build fixups
        #
        # Uv2nix can only work with what it has, and uv.lock is missing
        # essential metadata to perform some builds.
        #
        # This is an additional overlay implementing build fixups.
        # See:
        # - https://pyproject-nix.github.io/uv2nix/FAQ.html
        pyprojectOverrides = final: prev: {
          # Implement build fixups here.
          # Note that uv2nix is _not_ using Nixpkgs buildPythonPackage.
          # It's using https://pyproject-nix.github.io/pyproject.nix/build.html
        };

        # Construct package set
        pythonSet =
          # Use base package set from pyproject.nix builders
          (pkgs.callPackage pyproject-nix.build.packages {
            inherit (pkgs) python;
          }).overrideScope (
            nixpkgs.lib.composeManyExtensions [
              pyproject-build-systems.overlays.default
              overlay
              pyprojectOverrides
            ]
          );

        runtimeDepsWithProject =
          workspace.deps.default
          // {
            autocodegen = workspace.projects.root;
          };

        pythonEnv =
          pythonSet.mkVirtualEnv "autocodegen-env" runtimeDepsWithProject;
      in {
        # Package a virtual environment as our main application.
        #
        # Enable no optional dependencies for production build.
        packages.default = pythonEnv;

        apps.default = {
          type = "app";
          program = "${pythonEnv}/bin/acg";
        };
      }
    );
}
