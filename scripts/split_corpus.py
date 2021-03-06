import argparse
import os
import re
import random
from shutil import copyfile

desc = """Split a directory of files into "train", "dev" and "test" directories.
All files not in either "train" or "dev" will go into "test".
"""
TRAIN_DEFAULT = 300
DEV_DEFAULT = 34
TOTAL_DEFAULT = 1.


# TEST on all the rest


def copy(src, dest, link=False):
    if link:
        try:
            os.symlink(src, dest)
        except (NotImplementedError, OSError):
            copyfile(src, dest)
    else:
        copyfile(src, dest)


def numeric(s):
    try:
        return int(re.findall("([0-9]+)", s)[-1])
    except (ValueError, IndexError) as e:
        raise ValueError("Cannot find numeric ID in '%s'" % s) from e


def not_split_dir(filename):
    return filename not in ("train", "dev", "test") and not filename.startswith(".")


def split_passages(directory, train, dev, total, link, quiet=False, shuffle=False):
    filenames = sorted(filter(not_split_dir, os.listdir(directory)), key=numeric)
    if shuffle:
        random.shuffle(filenames)
    if total < 1.:
        filenames = random.sample(filenames, int(len(filenames)*total))
    assert filenames, "No files to split"
    if train <= 1.0:
        train = int(len(filenames) * train)
    if dev <= 1.0:
        dev = int(len(filenames) * dev)
    assert train + dev <= len(filenames), "Not enough files to split: %d+%d>%d" % (train, dev, len(filenames))
    for subdirectory in "train", "dev", "test":
        os.makedirs(os.path.join(directory, subdirectory), exist_ok=True)
    test = (len(filenames) - train - dev)
    print("%d files to split: %d/%d/%d" % (len(filenames), train, dev, test))
    print_format = "Creating link in %s to: " if link else "Copying to %s: "
    if not quiet:
        print(print_format % "train", end="", flush=True)
    for f in filenames[:train]:
        copy(os.path.join(directory, f), os.path.join(directory, "train", f), link)
        if not quiet:
            print(f, end=" ", flush=True)
    if not quiet:
        print()
        print(print_format % "dev", end="", flush=True)
    for f in filenames[train:train + dev]:
        copy(os.path.join(directory, f), os.path.join(directory, "dev", f), link)
        if not quiet:
            print(f, end=" ", flush=True)
    if not quiet:
        print()
        print(print_format % "test", end="", flush=True)
    for f in filenames[train + dev:]:
        copy(os.path.join(directory, f), os.path.join(directory, "test", f), link)
        if not quiet:
            print(f, end=" ", flush=True)
    if not quiet:
        print()


def main(args):
    split_passages(os.path.abspath(args.directory), args.train, args.dev, args.total, link=args.link,
                   quiet=args.quiet, shuffle=args.shuffle)


if __name__ == "__main__":
    argparser = argparse.ArgumentParser(description=desc)
    argparser.add_argument("directory", default=".", nargs="?", help="directory to split (default: current directory)")
    argparser.add_argument("-t", "--train", type=float, default=TRAIN_DEFAULT,
                           help="size of train split (default: %d)" % TRAIN_DEFAULT)
    argparser.add_argument("-d", "--dev", type=float, default=DEV_DEFAULT,
                           help="size of dev split (default: %d)" % DEV_DEFAULT)
    argparser.add_argument("-total", "--total", type=float, default=TOTAL_DEFAULT,
                           help="proportion of data to use (default: %d)" % TOTAL_DEFAULT)
    argparser.add_argument("-l", "--link", action="store_true", help="create symbolic link instead of copying")
    argparser.add_argument("-q", "--quiet", action="store_true", help="less output")
    argparser.add_argument("-s", "--shuffle", action="store_true", help="shuffle corpus")
    main(argparser.parse_args())
