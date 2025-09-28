{
  description = "Toptle - Process monitor with terminal title integration";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        toptle = pkgs.python3Packages.buildPythonApplication {
          pname = "toptle";
          version = "0.1.1";
          format = "pyproject";

          src = ./.;

          nativeBuildInputs = with pkgs.python3Packages; [
            setuptools
            wheel
          ];

          propagatedBuildInputs = with pkgs.python3Packages; [
            psutil
          ];

          # Tests require interactive terminal features that don't work in nix build
          doCheck = false;

          meta = with pkgs.lib; {
            description = "Process monitor with terminal title integration";
            homepage = "https://github.com/YPares/toptle";
            license = licenses.mit;
            maintainers = [ ];
            platforms = platforms.unix;
          };
        };
      in
      {
        packages.default = toptle;
        packages.toptle = toptle;

        apps.default = flake-utils.lib.mkApp {
          drv = toptle;
          exePath = "/bin/toptle";
        };
      }
    );
}
