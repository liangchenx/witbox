#!/bin/bash

if [ $# != 1 ]
then
	echo "usage: $0 <boot directory>"
	exit 1
fi

boot=${1%/}

part=""
mp=""
while read mnt
do
	mnt=($mnt)
	mp=${mnt[1]}
	#if [ ${boot:0:${#mp}} == $mp ]
	if [ ${boot} == $mp ]
	then
		part=${mnt[0]}
		break
	fi
done < /proc/mounts

if [ "$part" == "" ]
then
	echo "No such mount point found! ($boot)"
	exit 1
fi

disk=${part%%[0-9]}

############# install grub #############
echo "installing grub to $boot for $disk ..."

grub_cmd=`which grub2-install`
if [ -z $grub_cmd ]
then
	grub_cmd="grub-install"
fi

$grub_cmd --boot-directory=$boot $disk

############# generate grub.cfg #############
if [ -d "$mp/grub2" ]
then
	grub_cfg="$mp/grub2/grub.cfg"
elif [ -d "$mp/grub" ]
then
	grub_cfg="$mp/grub/grub.cfg"
else
	echo "The grub directory does not exist!"
	exit 1
fi

echo "Generating $grub_cfg ..."
echo "GRUB_TIMEOUT=5" > $grub_cfg

for iso in `ls $mp/iso/*.iso`
do
	fn=`basename $iso`
	# FIXME!
	dist=(${fn//-/ })

	id=${dist[0]}
	ver=${dist[1]}

	echo "generating menuentry for $id-$ver ..."
	case $id in
	CentOS|RHEL|Fedora|OLinux)
		uuid=`blkid $part | sed 's/.*\sUUID="\([a-z0-9-]*\)"\s.*/\1/'`
		cfg="\tlinux (lo)/isolinux/vmlinuz repo=hd:UUID=$uuid:/iso/\n"
		cfg=$cfg"\tinitrd (lo)/isolinux/initrd.img"
		;;

	ubuntu)
		# FIXME
		cfg="\tlinux (lo)/casper/vmlinuz.efi boot=casper iso-scan/filename=/iso/$fn\n"
		cfg=$cfg"\tinitrd (lo)/casper/initrd.lz"
		;;
	*)
		echo "Warning: distribution $id not supported (skipped)!"
		continue
		;;
	esac

	echo -e "\nmenuentry '$id $ver Install' {" >> $grub_cfg
	echo -e "\tloopback lo /iso/$fn" >> $grub_cfg
	echo -e $cfg >> $grub_cfg
	echo -e "}" >> $grub_cfg
done

echo
