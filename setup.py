import logging
import sys
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from textwrap import dedent

from setuptools import setup
from setuptools.command.install import install as orig_install
from setuptools.command.sdist import sdist as orig_sdist


@contextmanager
def sys_path():
    orig_path = sys.path[:]
    sys.path.insert(0, str(Path.cwd() / "src"))
    try:
        yield
    finally:
        sys.path = orig_path


class install(orig_install):
    def finalize_options(self):
        """Force platlib install since non-python libraries are included."""
        super().finalize_options()
        self.install_lib = self.install_platlib

    def run(self):
        super().run()
        self.write_obj_lists()
        self.generate_files()

        self.copy_tree("data", self.install_data)

    def write_obj_lists(self):
        """Generate config file of keyword, check, and other object lists."""
        (base_dir := Path(self.install_lib) / "pkgcheck").mkdir(parents=True, exist_ok=True)
        objects_path = base_dir / "_objects.py"
        const_path = base_dir / "_const.py"
        verinfo_path = base_dir / "_verinfo.py"

        # hack to drop quotes on modules in generated files
        class _kls:
            def __init__(self, module):
                self.module = module

            def __repr__(self):
                return self.module

        with sys_path():
            from pkgcheck import objects

        modules = defaultdict(set)
        objs = defaultdict(list)
        for obj in ("KEYWORDS", "CHECKS", "REPORTERS"):
            for name, cls in getattr(objects, obj).items():
                parent, module = cls.__module__.rsplit(".", 1)
                modules[parent].add(module)
                objs[obj].append((name, _kls(f"{module}.{name}")))

        keywords = tuple(objs["KEYWORDS"])
        checks = tuple(objs["CHECKS"])
        reporters = tuple(objs["REPORTERS"])

        logging.info(f"writing objects to {objects_path!r}")
        with objects_path.open("w") as f:
            objects_path.chmod(0o644)
            for k, v in sorted(modules.items()):
                f.write(f"from {k} import {', '.join(sorted(v))}\n")
            f.write(
                dedent(
                    f"""\
                        KEYWORDS = {keywords}
                        CHECKS = {checks}
                        REPORTERS = {reporters}
                    """
                )
            )

        logging.info(f"writing path constants to {const_path!r}")
        with const_path.open("w") as f:
            const_path.chmod(0o644)
            f.write(
                dedent(
                    """\
                        from os.path import abspath, exists, join
                        import sys
                        INSTALL_PREFIX = abspath(sys.prefix)
                        if not exists(join(INSTALL_PREFIX, 'lib/pkgcore')):
                            INSTALL_PREFIX = abspath(sys.base_prefix)
                        DATA_PATH = join(INSTALL_PREFIX, 'share/pkgcheck')
                    """
                )
            )

        logging.info("generating version info")
        from snakeoil.version import get_git_version

        verinfo_path.write_text(f"version_info={get_git_version(Path(__file__).parent)!r}")

    def generate_files(self):
        with sys_path():
            from pkgcheck import base, objects
            from pkgcheck.addons import caches

        (dst := Path(self.install_data) / "share/pkgcheck").mkdir(parents=True, exist_ok=True)

        logging.info("Generating available scopes")
        (dst / "scopes").write_text("\n".join(base.scopes) + "\n")

        logging.info("Generating available cache types")
        cache_objs = caches.CachedAddon.caches.values()
        (dst / "caches").write_text("\n".join(x.type for x in cache_objs) + "\n")

        for obj in ("KEYWORDS", "CHECKS", "REPORTERS"):
            logging.info(f"Generating {obj.lower()} list")
            (dst / obj.lower()).write_text("\n".join(getattr(objects, obj)) + "\n")


class sdist(orig_sdist):
    def make_release_tree(self, base_dir, files):
        super().make_release_tree(base_dir, files)
        base_dir = Path(base_dir)

        if (man_page := Path(__file__).parent / "build/sphinx/man/pkgcheck.1").exists():
            (base_dir / "man").mkdir(parents=True, exist_ok=True)
            self.copy_file(
                man_page, base_dir / "man/pkgcheck.1", preserve_mode=False, preserve_times=False
            )

        logging.info("generating version info")
        from snakeoil.version import get_git_version

        (base_dir / "src/pkgcheck/_verinfo.py").write_text(
            f"version_info={get_git_version(Path(__file__).parent)!r}"
        )


setup(
    cmdclass={
        "install": install,
        "sdist": sdist,
    }
)
