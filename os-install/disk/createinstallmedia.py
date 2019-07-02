#!/usr/bin/env python3


import os
from optparse import OptionParser
import re
import shutil
import subprocess
import platform

# if [ $UID != 0 ]; then
# 	echo "must run as super user!"
# 	exit 1
# fi
os_type = platform.system()
if os_type != 'Linux':
    raise Exception(os_type + ' NOT supported!')

dist_serial = {}
for dist in ['RHEL','CentOS','Fedora','OL']:
    dist_serial[dist] = 'redhat'
for dist in ['Ubuntu','Debian']:
    dist_serial[dist] = 'debian'

def blk_tag(tag, dev):
    fd = os.popen('blkid -s {} {}'.format(tag, dev))
    for line in fd:
    # r = subprocess.check_output(['blkid', '-s', tag, dev])
        kv = line.strip().split('=')
        if len(kv) > 1:
            return kv[1].strip('"')
    return None

def linux_dist(iso):
    label = blk_tag('LABEL', iso)
    for dist in dist_serial:
        if label.startswith(dist):
            return dist_serial[dist]
    return None

# if os.getuid() != 0:
#     print('must run as super user!')
#     exit(1)

# usage() {
# 	echo "usage: $0 --isopath/-p <iso path> --volume/-m <mount point>"
# }
parser = OptionParser()
parser.add_option('-m','--volume',dest = 'volume',help = 'mount point')
parser.add_option('-p','--isopath',dest = 'isopath',help = 'path to ISO image')
(opts,args) = parser.parse_args()

if opts.isopath != None:
    repo = opts.isopath
else:
    repo = os.getcwd()

if opts.volume == None:
    parser.print_help()
    exit(1)

root = re.sub('/+$', '', opts.volume)
part = ''

if root == '' or not os.path.exists(repo):
    parser.print_help()
    exit(1)

for line in open('/proc/mounts').readlines():
    mnt = line.split()
    if root == mnt[1]:
        part = mnt[0]
        break

if part == '':
    print('No such mount point:', root)
    exit(1)

# FIXME: sdXN, mmcMpN, nvmeMpN
disk = re.sub('\d+$', '', part)
index = part.lstrip(disk)

boot_dir = root + '/boot'
iso_dir  = root + '/iso'

for d in [boot_dir, iso_dir]:
    if not os.path.exists(d):
        os.mkdir(d)

# ############### copy ISO ###############

if os.path.isdir(repo):
    src_list = []
    for iso in os.listdir(repo):
        if iso.endswith('.iso'):
            if linux_dist(iso) != None:
                src_list.append(iso)
            else:
                print('"{}" skipped'.format(iso))
    if len(src_list) == 0:
        print('No valid Linux ISO found in "{}"!'.format(repo))
        exit(1)
elif os.path.exists(repo) and linux_dist(repo) != None:
    src_list = [repo]
else:
    print("'{}' is invalid!".format(repo))
    exit(1)

iso_list = []
count = 0
for iso in src_list:
    count += 1
    print('[{}/{}]'.format(count, len(src_list)))

    dest_iso = iso_dir + '/' + os.path.basename(iso)
    iso_list.append(dest_iso)

    if os.path.exists(dest_iso):
        print(dest_iso + ' already exists!')
    else:
        shutil.copyfile(iso, dest_iso)

############# install grub #############

print("installing grub to {} for {} ...".format(boot_dir, disk))

grub_cfg = None
for grub in ['grub', 'grub2']:
    grub_cmd = grub + '-install'
    if shutil.which(grub_cmd) != None:
        grub_cfg = boot_dir + '/' + grub + '/grub.cfg'
        break

if grub_cfg == None:
	print("No grub installer found!")
	exit(1)

pttype = blk_tag('PTTYPE', disk)
print("{} partition type: {}".format(disk, pttype))

if pttype == 'gpt':
    grub_cmd += ' --target=x86_64-efi'

    esp = None
    fd = os.popen('parted ' + disk + ' print')
    for line in fd:
        fields = line.strip().split()
        if len(fields) > 0 and fields[0].isdigit() and 'esp' in fields:
            esp = fields[0]
            break
    if esp == None:
        print("ESP partition not found!")
        exit(1)

    for part in os.listdir('/dev'):
        if re.match(disk + '\d+', part): # or + '\d+p\d+'
            subprocess.call('umount ' + part)

    efi_dir = boot_dir + '/efi'
    if not os.path.exists(efi_dir):
        os.mkdir(efi_dir)
    subprocess.call('mount {}{} {}'.format(disk, esp, efi_dir), shell=True)
else:
	grub_cmd += ' --target=i386-pc'

for g in ['grub', 'grub2']:
    grub_dir = boot_dir + '/' + g
    if os.path.exists(grub_dir):
        shutil.rmtree(grub_dir)

subprocess.call("{} --removable --boot-directory={} {}".format(grub_cmd, boot_dir, disk), shell=True)

print("Generating {} ...".format(grub_cfg))

cf = open(grub_cfg, 'w')

configs = ['GRUB_TIMEOUT=5',
    'insmod ext2',
    'insmod all_video'
]
if pttype == 'gpt':
    configs.append('insmod part_gpt')

cf.writelines(configs)

for iso in iso_list:
    iso_rel = iso.lstrip(root)
    label = blk_tag('LABEL', iso)

    print("{} ({})".format(label, iso_rel))

    if linux_dist(iso) == 'redhat':
        uuid = blk_tag('UUID', part)
        linux="isolinux/vmlinuz repo=hd:UUID={}:{}".format(uuid, iso_dir.lstrip(root))
        initrd="isolinux/initrd.img"
    elif linux_dist(iso) == 'debian':
        linux="casper/vmlinuz.efi boot=casper iso-scan/filename=" + iso_rel
        initrd="casper/initrd.lz"
    else:
        print('Warning: "{}" skipped!'.format(iso))
        continue

    menuentry = [
        "menuentry 'Install " + label + " {",
        "    set root='hd0,{}'".format(index),
        "    loopback lo {}".format(iso_rel),
        "    linux (lo)/{}".format(linux),
        "    initrd (lo)/{}".format(initrd),
        "}"
    ]
    cf.writelines(menuentry)

if pttype == 'gpt':
    subprocess.call('umount {}/efi'.format(boot_dir), shell=True)