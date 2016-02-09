#!/usr/bin/python

width = 16
height = 16

print('%d tiles wide' % (width / 8))
print('%d tiles high' % (height / 8))

tile_width = width / 8
tile_height = height / 8

idx = 0

# sheet is composed of 8x8 tiles
for tile_y in range(tile_height):
    for tile_x in range(tile_width):

        # tile is composed of 2x2, 4x4 blocks
        for y in range(2):
            for x in range(2):

                # each block is packed in column order
                for y2 in range(4):
                    for x2 in range(4):
                        pixel_x = x2 + (x * 4) + (tile_x * 8)
                        pixel_y = y2 + (y * 4) + (tile_y * 8)

                        print('(%d, %d) -> (%d, %d) -> (%d, %d) = (%d, %d) [%d]' %
                              (tile_x, tile_y, x, y, x2, y2, pixel_x, pixel_y, idx))
                        idx += 1
                print('')

        # # tile is composed of 2x2 sub-tiles
        # for y in range(2):
        #     for x in range(2):
        #
        #         # sub-tile is composed of 2x2 pixel groups
        #         for y2 in range(2):
        #             for x2 in range(2):
        #
        #                 # pixel group is composed of 2x2 pixels (finally)
        #                 for y3 in range(2):
        #                     for x3 in range(2):
        #                         if tile_y + y + y2 + y3 >= height:
        #                             continue
        #                         if tile_x + x + x2 + x3 >= width:
        #                             continue
        #
        #                         pixel_x = (x3 + (x2 * 2) + (x * 4) + (tile_x * 8))
        #                         pixel_y = (y3 + (y2 * 2) + (y * 4) + (tile_y * 8))
        #
        #                         data_pos = ((x3 + (x2 * 4) + (x * 16) + (tile_x * 64)) + ((y3 * 2) + (y2 * 8) + (y * 32) + (tile_y * 64)))
        #
        #                         print('(%d, %d) -> (%d, %d) -> (%d, %d) -> (%d, %d) = %d (%d, %d) [%d]' %
        #                               (tile_x, tile_y, x, y, x2, y2, x3, y3, data_pos, pixel_x, pixel_y, pixel_x + pixel_y * width))
        #
        #                 print('')
        #
        #         print('')

        print('')
