# bbd_lz_rle
Mixed LZ-RLE compression tool for for Battle B-Daman Atlus GBA games.


Synopsis:
```
bbd_lz_rle.py COMMAND [OPTIONS] FILE_NAME
```
  
Description:
```
bbd_lz_rle.py unpack [OPTIONS] IN_NAME

  Decompress packed block from given IN_NAME file. Offset and output file
  name can be provided, otherwise default '0' and 'decompressed.bin' will be
  used.

Options:
  -a, --address TEXT   Offset of compressed block start.
  -o, --out_name TEXT  Output plain file name.
  
bbd_lz_rle.py pack [OPTIONS] IN_NAME

  Compress plain IN_NAME file. Output file name can be provided, otherwise
  default 'compressed.bin' will be used.

Options:
  -o, --out_name TEXT  Output packed file name.
```

For usage details see additional files in [release](https://github.com/romhack/bbd_lz_rle/releases/latest) archive. 
  
A tool for compressing and decompressing data in GameBoy Advance games: 
 - 1606 - B-Densetsu! Battle B-Daman - Moero! B-Tamashii! (J)
 - 2414 - B-Densetsu! Battle B-Daman - Fire Spirit! Honootamashii! (J)
 - 2463 - Battle B-Daman (U)
 - 2507 - Battle B-Daman - Fire Spirits (U)  
 
and possibly other Atlus games. Compression is used mostly for graphics data, such as tiles and tilemaps. For tiles this tool shows 3-5% better compression than original packer, and same or slightly better compression for other data.
Compression format description: 
```
RLE:
1 YYYYY XX  XXXXXXXX AAAAAAAA...
| |     |            |
| |     |            chunk to repeat
| |     rle decompress chunks count (plain length in case of 1 byte RLE)
| chunk size - 1 (if 0, you repeat next 1 byte, 1: repeat next word, etc.)
compression flag

LZ:     
1 11111 XX XXXXXXXX ZZZZZZZZ ZZZZZZZZ
| |     |           |
| |     |           16 bit lz offset
| |     lz decompress length
| signifies LZ copy
compression flag

LZ also works if length > (current_position - offset), effectively unpacking from currently unpacked buffer.
For LZ to be more effective, than worst case 'fresh' raw dump, you need to lz encode 4 bytes length

Raw:
0 XXXXXXX AAAAAAAA...(bytes to copy)
| |     
| |     
| copy length (zero length signifies end of compressed block)
non-compression flag

```