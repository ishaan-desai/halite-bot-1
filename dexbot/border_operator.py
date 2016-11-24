"""Handle the logistics of teamwork to capture border areas."""


import numpy as np
import dexbot.loupes as loupes
from dexbot.move_queue import PendingMoves

class BorderOperator(object):

    def __init__(self, map_state):
        self.width = map_state.width
        self.height = map_state.height

    def set_border_value(self, map_state, appraiser):
        sort_value = np.argsort(-1 * appraiser.brdr_value)

        self.impt_locs = [(r[0], r[1]) for r in appraiser.brdr_locs[sort_value]]
        self.brdr_value = appraiser.brdr_value[sort_value]

        self.impt_locs = [self.impt_locs[i] for i in range(len(self.impt_locs))
                          # if self.brdr_value[i] > np.percentile(self.brdr_value, 65)]
                          if self.brdr_value[i] >= self.brdr_value.mean()]

    def get_moves(self, map_state):
        ic_queue = self.get_immediate_captures(self.impt_locs, map_state)

        rem_locs = [loc for loc in self.impt_locs
                    if not loc in ic_queue.locs]
        bm_queue = self.get_border_moves(rem_locs, map_state)

        return ic_queue, bm_queue

    def get_immediate_captures(self, rem_locs, map_state):
        pm = PendingMoves()

        for x, y in rem_locs:
            target_str = map_state.strn[x, y]

            nx, ny = (x+1) % self.width, y
            if map_state.mine[nx, ny] and \
                    (map_state.mine_strn[nx, ny] > target_str or
                     map_state.mine_strn[nx, ny] >= 255):
                pm.pend_move(nx, ny, 4)
                map_state.register_move(nx, ny, 4)
                # with open('pending.txt', 'a') as f:
                #     f.write('CapImmediate:\t' + repr((nx, ny)) + '\t' + repr(4) + '\n')

                continue

            nx, ny = (x-1) % self.width, y
            if map_state.mine[nx, ny] and \
                    (map_state.mine_strn[nx, ny] > target_str or
                     map_state.mine_strn[nx, ny] >= 255):
                pm.pend_move(nx, ny, 2)
                map_state.register_move(nx, ny, 2)
                # with open('pending.txt', 'a') as f:
                #     f.write('CapImmediate:\t' + repr((nx, ny)) + '\t' + repr(2) + '\n')

                continue

            nx, ny = x, (y+1) % self.height
            if map_state.mine[nx, ny] and \
                    (map_state.mine_strn[nx, ny] > target_str or
                     map_state.mine_strn[nx, ny] >= 255):
                pm.pend_move(nx, ny, 1)
                map_state.register_move(nx, ny, 1)
                # with open('pending.txt', 'a') as f:
                #     f.write('CapImmediate:\t' + repr((nx, ny)) + '\t' + repr(1) + '\n')

                continue

            nx, ny = x, (y-1) % self.height
            if map_state.mine[nx, ny] and \
                    (map_state.mine_strn[nx, ny] > target_str or
                     map_state.mine_strn[nx, ny] >= 255):
                pm.pend_move(nx, ny, 3)
                map_state.register_move(nx, ny, 3)
                # with open('pending.txt', 'a') as f:
                #     f.write('CapImmediate:\t' + repr((nx, ny)) + '\t' + repr(3) + '\n')

                continue

        return pm

    def get_border_moves(self, rem_locs, map_state):
        pm = PendingMoves()

        for x, y in rem_locs:
            target_str = map_state.strn[x, y]

            if map_state.mine[(x+1) % self.width, y]:  # Has self to east
                nx, ny = (x+1) % self.width, y
                self._move_by_loupe(x, y, nx, ny,
                                    loupes.east,
                                    pm, map_state, target_str)

            elif map_state.mine[(x-1) % self.width, y]:  # Has self to west
                nx, ny = (x-1) % self.width, y
                self._move_by_loupe(x, y, nx, ny,
                                    loupes.west,
                                    pm, map_state, target_str)

            elif map_state.mine[x, (y+1) % self.height]:  # Has self to south
                nx, ny = x, (y+1) % self.height
                self._move_by_loupe(x, y, nx, ny,
                                    loupes.south,
                                    pm, map_state, target_str)

            elif map_state.mine[x, (y-1) % self.height]:  # Has self to north
                nx, ny = x, (y-1) % self.height
                self._move_by_loupe(x, y, nx, ny,
                                    loupes.north,
                                    pm, map_state, target_str)

        return pm

    def _move_by_loupe(self, x, y, nx, ny, loupe,
                       pm, map_state, target_str):
        teamup_coords = (loupe.locs + (x, y)) % (self.width, self.height)

        strs = np.zeros(len(teamup_coords), dtype=int)
        for i, (tx, ty) in enumerate(teamup_coords):
            strs[i] = map_state.mine_strn[tx, ty]

        if map_state.prod[nx, ny] + map_state.strn[nx, ny] > target_str:
            pm.pend_move(nx, ny, 0)
            map_state.register_move(nx, ny, 0)
            # with open('pending.txt', 'a') as f:
            #     f.write('CCGNext:\t' + repr((nx, ny)) + '\t' + repr(0) + '\n')

        elif strs.sum() > target_str + map_state.prod[nx, ny]:
            str_order = np.argsort(strs)
            assigned_strength = 0
            for i in str_order:
                (lx, ly), cardinal = loupe.locs[i], loupe.dirs[i]
                xlx, yly = (x+lx) % self.width, (y+ly) % self.height
                if map_state.mine[xlx, yly]:
                    pm.pend_move(xlx, yly, cardinal)
                    map_state.register_move(xlx, yly, cardinal)
                    assigned_strength += map_state.mine_strn[xlx, yly]
                # with open('pending.txt', 'a') as f:
                #     f.write('CCGNow:\t' + repr((xlx, yly)) + '\t' + repr(cardinal) + '\n')
                if assigned_strength > (target_str - map_state.prod[nx, ny]):
                    break
            # for (lx, ly), cardinal in loupe.items():
            #     xlx, yly = (x+lx) % self.width, (y+ly) % self.height
            #     if map_state.mine[xlx, yly]:
            #         pm.pend_move(xlx, yly, cardinal)
            #         map_state.register_move(xlx, yly, cardinal)
