# names of the three ghost mount-points
for m in "6 E2E" "FTG_E2E" "FFBK 6"; do
  sudo mkdir -p "/Volumes/$m"          # recreate the path
  sudo umount -f "/Volumes/$m"         # force-unmount the SMB volume
  sudo rmdir "/Volumes/$m"             # clean up
done