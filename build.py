#!/usr/bin/env python3
"""One-command DOL build for macOS, Linux and Windows.

    python3 build.py            # GameCube DOL (build/cube/src/reVC.dol)
    python3 build.py wii        # Wii dev DOL (build/wii/src/reVC.dol)
    python3 build.py all        # both

Needs a devkitPro install with the GameCube/Wii toolchains (see README).
Everything else the build needs ships in this repository.
"""
import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
DKP_GROUPS = ["gamecube-dev", "wii-dev"]
# Per-OS repos needed on top of the shared [dkp-libs] one: repo name and the
# server path suffix under https://pkg.devkitpro.org/packages.
DKP_REPO_HOSTS = {
    "linux": ("dkp-linux", "linux/$arch/"),
    "macos": ("dkp-macos", "macos/$arch/"),
    "windows": ("dkp-windows", "windows/$arch/"),
}
LIBRW_SRC = os.path.join(ROOT, "vendor", "librw")
GX_FORCE_RE = re.compile(r"^(#define\s+GX_FORCE_PROGRESSIVE\s+)\w+")


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, check=True, **kw)


def github_latest_asset(repo, match):
    with urllib.request.urlopen(
            f"https://api.github.com/repos/{repo}/releases/latest") as r:
        release = json.load(r)
    for asset in release["assets"]:
        if match in asset["name"]:
            return asset["name"], asset["browser_download_url"]
    sys.exit(f"no release asset matching '{match}' in {repo}")


def download(url, name):
    path = os.path.join(tempfile.gettempdir(), name)
    print(f"+ download {url}")
    urllib.request.urlretrieve(url, path)
    return path


def dkp_install_groups(pacman="dkp-pacman", sudo=True):
    cmd = (["sudo"] if sudo else []) + [pacman, "-Sy", "--noconfirm",
                                        "--needed"] + DKP_GROUPS
    run(cmd)


def setup_macos():
    if shutil.which("brew"):
        run(["brew", "install", "--quiet", "cmake", "ninja"])
    else:
        print("Homebrew not found; install cmake and ninja yourself.")
    if not shutil.which("dkp-pacman"):
        name, url = github_latest_asset("devkitPro/pacman", ".pkg")
        pkg = download(url, name)
        run(["sudo", "installer", "-pkg", pkg, "-target", "/"])
    ensure_dkp_repos()
    dkp_install_groups()


def setup_linux():
    if shutil.which("apt-get"):
        run(["sudo", "apt-get", "install", "-y", "cmake", "ninja-build",
             "wget"])
        if not shutil.which("dkp-pacman"):
            script = download(
                "https://apt.devkitpro.org/install-devkitpro-pacman",
                "install-devkitpro-pacman")
            os.chmod(script, 0o755)
            run(["sudo", "bash", script])
        dkp_install_groups()

    elif shutil.which("dnf"):
        try:
            run(["sudo", "dnf", "install", "-y", "cmake", "ninja-build", "wget"])
            if not shutil.which("pacman"):
                print("Pacman is not installed in this OS. Installing.....")
                run(["sudo", "dnf", "install", "-y", "pacman"])

            # Instalamos las llaves
            run(["sudo", "pacman-key", "--init"])
            run(["sudo", "pacman-key", "--recv",
                "BC26F752D25B92CE272E0F44F7FD5492264BB9D0",
                "--keyserver", "keyserver.ubuntu.com"])
            run(["sudo", "pacman-key", "--lsign",
                "BC26F752D25B92CE272E0F44F7FD5492264BB9D0"])

            ensure_dkp_repos()
            dkp_install_groups("pacman")
                
        except:
            sys.exit("Install devkitPro from the official documentation: "
                    "https://devkitpro.org/wiki/devkitPro_pacman")
            
    elif shutil.which("pacman"):
        run(["sudo", "pacman", "-S", "--needed", "--noconfirm", "cmake",
             "ninja"])
        pacman = "dkp-pacman" if shutil.which("dkp-pacman") else "pacman"
        if pacman == "pacman":
            print("Add the devkitPro repositories to /etc/pacman.conf first "
                  "if this fails: https://devkitpro.org/wiki/devkitPro_pacman")
        dkp_install_groups(pacman)
    else:
        sys.exit("Neither apt-get, dnf nor pacman found; install devkitPro "
                 "manually: https://devkitpro.org/wiki/Getting_Started")


def setup_windows():
    if shutil.which("winget"):
        for pkg in ("Kitware.CMake", "Ninja-build.Ninja"):
            subprocess.run(["winget", "install", "-e", "--id", pkg,
                            "--accept-package-agreements",
                            "--accept-source-agreements"])
    else:
        print("winget not found; install cmake and ninja yourself.")
    if not os.path.isdir("C:/devkitPro"):
        name, url = github_latest_asset("devkitPro/installer", ".exe")
        exe = download(url, name)
        print("Launching the devkitPro installer — select the GameCube and "
              "Wii development packages.")
        os.startfile(exe)  # noqa: attribute exists on Windows
    else:
        print("devkitPro found at C:/devkitPro; run the devkitPro updater "
              "to add gamecube-dev and wii-dev if they are missing.")
    ensure_dkp_repos()


def setup():
    system = platform.system()
    try:
        if system == "Darwin":
            setup_macos()
        elif system == "Linux":
            setup_linux()
        elif system == "Windows":
            setup_windows()
        else:
            sys.exit(f"unsupported OS: {system}")
    except (subprocess.CalledProcessError, OSError) as error:
        sys.exit(f"setup step failed ({error}); the README lists the manual "
                 "installation steps for every OS.")
    print("\nSetup done. Now run: python3 build.py")


def find_devkitpro(required=True):
    for candidate in (os.environ.get("DEVKITPRO"), "/opt/devkitpro",
                      "C:/devkitPro", "C:\\devkitPro"):
        if candidate and os.path.isfile(
                os.path.join(candidate, "cmake", "ogc-common.cmake")):
            return candidate.replace("\\", "/")
    if not required:
        return None
    sys.exit("devkitPro not found. Install it (with GameCube/Wii packages) "
             "and/or set the DEVKITPRO environment variable.")


def dkp_pacman_conf(host):
    """Return this OS's pacman.conf, or None when devkitPro is not found."""
    if host == "linux":
        return "/etc/pacman.conf"
    dkp = find_devkitpro(required=False)
    if host == "macos":
        return (os.path.join(dkp, "pacman", "etc", "pacman.conf")
                if dkp else None)
    # windows: devkitPro ships its own MSYS2 beside the SDK; fall back to a
    # manual MSYS2 install.
    roots = [dkp, os.environ.get("DEVKITPRO"), "C:/devkitPro", "C:\\devkitPro"]
    confs = [os.path.join(root, rel, "etc", "pacman.conf")
             for root in roots if root
             for rel in ("MSYS2", "msys64")]
    confs += [os.path.join(root, "etc", "pacman.conf")
              for root in ("C:/msys64", "C:/msys2")]
    return next((conf for conf in confs if os.path.isfile(conf)), None)


def ensure_dkp_repos():
    """Add the devkitPro pacman repositories for this OS.

    The devkitPro installer preconfigures them ([dkp-libs] plus the per-OS
    repo), so this is a silent safety net that only appends what is missing;
    the one case that really needs it is Fedora, whose setup_linux uses the
    system pacman. macOS and Windows keep their own pacman.conf inside the
    devkitPro installation.
    """
    if platform.system() == "Linux":
        host, sudo = "linux", True
    elif platform.system() == "Darwin":
        host, sudo = "macos", True
    elif platform.system() == "Windows":
        host, sudo = "windows", False
    else:
        sys.exit(f"unsupported OS: {platform.system()}")
    conf = dkp_pacman_conf(host)
    if not conf:
        print("devkitPro pacman.conf not found; add the devkitPro repositories "
              "manually (see the README for your OS).")
        return
    try:
        with open(conf, errors="replace") as f:
            content = f.read()
    except OSError as error:
        print(f"cannot read {conf} ({error}); add the devkitPro repositories "
              "manually (see the README for your OS).")
        return

    repo, path = DKP_REPO_HOSTS[host]
    missing = []
    if "[dkp-libs]" not in content:
        missing.append("[dkp-libs]\n"
                       "Server = https://pkg.devkitpro.org/packages")
    if f"[{repo}]" not in content:
        missing.append(f"[{repo}]\n"
                       f"Server = https://pkg.devkitpro.org/packages/{path}")
    if not missing:
        return
    block = "\n# FOR DEVKITPRO\n" + "\n\n".join(missing) + "\n"
    try:
        with open(conf, "a") as f:
            f.write(block)
    except PermissionError:
        if sudo:
            subprocess.run(["sudo", "tee", "-a", conf],
                           input=block.encode(), check=True)
        else:
            print(f"cannot write {conf}; add the devkitPro repositories "
                  "manually (see the README for your OS).")


def find_tool(name, dkp):
    tool = shutil.which(name)
    if tool:
        return tool
    bundled = os.path.join(dkp, "tools", "bin", name)
    for path in (bundled, bundled + ".exe"):
        if os.path.isfile(path):
            return path
    sys.exit(f"{name} not found on PATH; install it or add it to PATH.")


def gx_patch(video):
    """Bake the GameCube video mode into the pinned librw submodule.

    vendor/librw/src/gx/gx.cpp hard-defines GX_FORCE_PROGRESSIVE=1 with no
    #ifndef guard, so no -D can override it: the value can only be baked at
    compile time by editing that file. The cube build is 480i composite, so
    the one line is re-written transiently and always restored in a finally,
    leaving the submodule working tree pristine on success and on failure
    alike. Its HEAD and commits are never touched.
    """
    value = 1 if video == "progressive" else 0
    gx = os.path.join(LIBRW_SRC, "src", "gx", "gx.cpp")
    with open(gx) as f:
        lines = f.readlines()
    for i, line in enumerate(lines):
        if GX_FORCE_RE.match(line):
            lines[i] = GX_FORCE_RE.sub(rf"\g<1>{value}", line)
            break
    else:
        sys.exit("{}: GX_FORCE_PROGRESSIVE define not found".format(gx))
    with open(gx, "w") as f:
        f.writelines(lines)


def gx_restore():
    subprocess.run(["git", "-C", LIBRW_SRC, "restore", "--", "src/gx/gx.cpp"],
                   check=True)


def build(target, dkp, cmake, ninja, video):
    if target == "cube":
        toolchain = f"{dkp}/cmake/GameCube.cmake"
    else:
        toolchain = os.path.join(ROOT, "vendor", "portlibs", "cmake",
                                 "Wii.cmake")
    build_dir = os.path.join(ROOT, "build", target)
    os.makedirs(build_dir, exist_ok=True)
    env = dict(os.environ, DEVKITPRO=dkp)
    patched = target == "cube"
    if patched:
        # Clean the file even if a previous run was interrupted mid-build,
        # then rewrite it for the chosen mode for the duration of this build.
        gx_restore()
        gx_patch(video)
    try:
        if not os.path.isfile(os.path.join(build_dir, "build.ninja")):
            subprocess.run([
                cmake, "-G", "Ninja", "-S", ROOT, "-B", build_dir,
                "-DCMAKE_BUILD_TYPE=Release",
                f"-DCMAKE_TOOLCHAIN_FILE={toolchain}",
                "-DLIBRW_PLATFORM=GAMECUBE",
                "-DDKP_OGC_PLATFORM_LIBRARY=libogc2",
                "-DREVC_THEORA_ROOT=" + os.path.join(ROOT, "vendor", "portlibs",
                                                     "ppc"),
            ], check=True, env=env)
        subprocess.run([ninja, "-C", build_dir], check=True, env=env)
    finally:
        if patched:
            gx_restore()
    dol = os.path.join(build_dir, "src", "reVC.dol")
    print(f"\n  {target}: {dol}")


def build_txdconv():
    """Host-compile the ahead-of-time texture converter against librw."""
    host_dir = os.path.join(ROOT, "build", "host")
    librw = os.path.join(ROOT, "vendor", "librw")
    cmake = shutil.which("cmake") or sys.exit("cmake not found")
    ninja = shutil.which("ninja") or sys.exit("ninja not found")
    if not os.path.isfile(os.path.join(host_dir, "build.ninja")):
        run([cmake, "-G", "Ninja", "-S", librw, "-B", host_dir,
             "-DCMAKE_BUILD_TYPE=Release", "-DLIBRW_PLATFORM=NULL",
             "-DLIBRW_TOOLS=OFF", "-DLIBRW_INSTALL=OFF"])
    run([ninja, "-C", host_dir])
    exe = os.path.join(host_dir, "txdconv")
    src = os.path.join(ROOT, "tools", "gamecube", "txdconv.cpp")
    lib = None
    for cand in ("src/librw.a", "librw.a", "src/librw.lib"):
        if os.path.isfile(os.path.join(host_dir, cand)):
            lib = os.path.join(host_dir, cand)
            break
    if lib is None:
        sys.exit("host librw static library not found under build/host")
    if (not os.path.isfile(exe) or
            os.path.getmtime(exe) < os.path.getmtime(src)):
        cxx = (os.environ.get("CXX") or shutil.which("c++") or
               shutil.which("g++") or shutil.which("clang++"))
        if not cxx:
            sys.exit("no host C++ compiler found (set CXX)")
        run([cxx, "-O2", "-std=c++14", src, f"-I{librw}", lib, "-o", exe])
    return exe


def build_sd(args):
    """Drive tools/gamecube/build_sd.py with assets/ conventions."""
    game = args.game or os.path.join(ROOT, "assets", "GTAVC")
    if not os.path.isdir(game):
        sys.exit(f"game data not found at {game}; copy your Vice City "
                 "install there or pass --game (see assets/README.md)")
    out = args.out or os.path.join(ROOT, "assets", "sd-tree")
    cmd = [sys.executable,
           os.path.join(ROOT, "tools", "gamecube", "build_sd.py"),
           "--game", game, "--out", out,
           "--txdconv", build_txdconv()]
    if args.keep_sfx_raw:
        cmd.append("--keep-sfx-raw")
    audio = args.audio or os.path.join(ROOT, "assets", "audio-ogg")
    inner = os.path.join(audio, "audio")
    if os.path.isdir(inner):
        audio = inner   # convert_audio escribe en un subdir audio/
    if os.path.isdir(audio):
        cmd += ["--audio", audio]
    movies = args.movies or os.path.join(ROOT, "assets", "movies")
    if os.path.isdir(movies):
        cmd += ["--preencoded-movies", movies]
    run(cmd)
    print(f"\n  SD card tree: {out}  (copy its CONTENTS to the card root)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", default="cube",
                        choices=("cube", "wii", "all", "sd"))
    parser.add_argument("--game", help="Vice City install "
                        "(default: assets/GTAVC)")
    parser.add_argument("--out", help="SD tree output "
                        "(default: assets/sd-tree)")
    parser.add_argument("--audio", help="converted audio dir "
                        "(default: assets/audio-ogg if present)")
    parser.add_argument("--movies", help="pre-encoded movies dir "
                        "(default: assets/movies if present)")
    parser.add_argument("--setup", action="store_true",
                        help="install the build dependencies for this OS "
                             "(brew / apt / pacman / winget + devkitPro)")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--keep-sfx-raw", action="store_true",
                help="keep the unpacked sample bank for an SD-only build")
    parser.add_argument("--video", choices=("composite", "progressive"),
                default="composite", help="GameCube video mode (cube only): "
                                           "composite = 480i (DOL-101); "
                                           "progressive = 480p (GCHD). "
                                           "Baked into librw at build time.")
    args = parser.parse_args()
    if args.self_test:
        assert callable(build) and callable(setup) and ROOT
        print("build.py self-test passed")
        return
    if args.setup:
        setup()
        return
    if args.target == "sd":
        build_sd(args)
        return
    dkp = find_devkitpro()
    cmake = find_tool("cmake", dkp)
    ninja = find_tool("ninja", dkp)
    for target in ("cube", "wii") if args.target == "all" else (args.target,):
        video = args.video if target == "cube" else None
        build(target, dkp, cmake, ninja, video)


if __name__ == "__main__":
    main()
