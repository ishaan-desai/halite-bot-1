"""Highly mechanical class that takes care of avoiding the cap."""


import numpy as np
from dexlib.find_path import find_pref_next


import logging
logging.basicConfig(filename='wtf.info', level=logging.DEBUG, filemode="w")


class Resolver:
    """Handle str cap avoiding, patch mechanics, etc."""

    def __init__(self, gm, strlim=255):
        self.strlim = strlim

    def resolve(self, gm, moveset):
        # I don't do anything about over-growing the cap, but can I even.
        moveset.set_stays()

        pstrn_map = np.zeros_like(gm.strn)

        on_moves = {(ax, ay): v for (ax, ay), v in moveset.move_dict.items()
                    if ((ax + ay + gm.turn) % 2 == gm.parity)}  # or gm.noncombat[ax, ay]}
        off_moves = {(ax, ay): v for (ax, ay), v in moveset.move_dict.items()
                     if ((ax + ay + gm.turn) % 2 != gm.parity)}  # and not gm.noncombat[ax, ay]}

        if (gm.turn < 40 and not gm.in_combat) or gm.turn == gm.last_turn:
            on_moves = moveset.move_dict
            off_moves = {}

        # Handle all the black squares going where they need to be
        on_origins = list(on_moves.keys())
        on_targets = list(on_moves.values())
        on_strns = [gm.strn[x, y] for (x, y) in on_origins]
        # on_dists = [gm.dists[x, y, a, b] - (gm.strn[x, y] / 1000)
        #             for ((x, y), (a, b, _)) in zip(on_origins, on_targets)]
        str_sort = np.argsort(on_strns)

        for i in str_sort[::-1]:
            ax, ay = on_origins[i]
            tx, ty, _ = on_targets[i]
            istrn = on_strns[i]
            strlim_cell = max(istrn, self.strlim)

            if gm.close_to_combat[ax, ay] and not (ax == tx and ay == ty):
                d2c = gm.dist_from_combat[ax, ay]
                choices = []
                cdists = []
                for i, (nx, ny) in enumerate(gm.nbrs[ax, ay]):
                    if gm.dist_from_combat[nx, ny] < d2c and not gm.wall[nx, ny]:
                        choices.append((nx, ny, i + 1))
                        cdists.append(gm.dists[tx, ty, nx, ny] + gm.prod[nx, ny] * 0.01)

                if len(choices) == 2:
                    argsort = np.argsort(cdists)
                    best = argsort[0]
                    secnd = argsort[1]
                    (px1, py1, d1), (px2, py2, d2) = choices[best], choices[secnd]
                elif len(choices):
                    (px1, py1, d1), (px2, py2, d2) = choices[0], (None, None, None)
                else:
                    (px1, py1, d1), (px2, py2, d2) = (ax, ay, 0), (None, None, None)

                # logging.debug(((ax, ay), choices))
            else:
                (px1, py1, d1), (px2, py2, d2) = find_pref_next(ax, ay, tx, ty, gm)

            if (istrn + pstrn_map[px1, py1]) <= strlim_cell:  # and \
                    #  ((gm.strn[px1, py1] + gm.prod[px1, py1]) < istrn or
                    #    gm.owned[px1, py1] == 0):
                moveset.add_move(ax, ay, px1, py1, d1)
                pstrn_map[px1, py1] += istrn

                # logging.info(('Priority:', ax, ay, px1, py1, istrn, pstrn_map[px1, py1]))
                # logging.debug(((ax, ay), 'to', (d1), 'firstpick'))
            elif px2 is not None and (istrn + pstrn_map[px2, py2]) <= strlim_cell:  # and \
                    #  ((gm.strn[px2, py2] + gm.prod[px2, py2]) < istrn or
                    #    gm.owned[px2, py2] == 0):
                moveset.add_move(ax, ay, px2, py2, d2)
                pstrn_map[px2, py2] += istrn

                # logging.info(('Priority:', ax, ay, px2, py2, istrn, pstrn_map[px2, py2]))
                # logging.debug(((ax, ay), 'to', (d2), 'secpick'))
            elif gm.melee_mat[ax, ay]:
                nbrs = gm.nbrs[(ax, ay)]
                scores = np.array([
                    gm.combat_heur[nx, ny] * ((pstrn_map[nx, ny] + istrn) < strlim_cell)
                    #  + (gm.wall[nx, ny] * -1000)
                    for (nx, ny) in nbrs
                ])

                if scores.max() > 0:
                    nx, ny = nbrs[scores.argmax()]
                    dir_ = self.nxny_to_cardinal(gm, ax, ay, nx, ny)
                    moveset.add_move(ax, ay, ax, ay, dir_)
                    pstrn_map[nx, ny] += istrn + gm.prod[ax, ay]
                else:
                    moveset.add_move(ax, ay, ax, ay, 0)
                    pstrn_map[ax, ay] += istrn + gm.prod[ax, ay]

            else:
                # moveset.add_move(ax, ay, ax, ay, 0)
                # pstrn_map[ax, ay] += istrn + gm.prod[ax, ay]
                off_moves[ax, ay] = tx, ty
                # logging.debug(((ax, ay), 'to', (0), 'dodgeroo'))

        # Handle all the white squares getting the heck out of the way
        # Not iterating in any particular order!
        for (ax, ay) in off_moves.keys():
            d2c = gm.dist_from_combat[ax, ay]
            istrn = gm.strnc[ax, ay]
            iprod = gm.prod[ax, ay]
            strlim_cell = max(istrn, self.strlim)

            if pstrn_map[ax, ay] == 0:
                moveset.add_move(ax, ay, ax, ay, 0)
                pstrn_map[ax, ay] += istrn + iprod
                # logging.info(('dodge', ax, ay, 'safe to stay1', istrn, pstrn_map[ax, ay]))

            elif (pstrn_map[ax, ay] + istrn + iprod) <= strlim_cell:
                moveset.add_move(ax, ay, ax, ay, 0)
                pstrn_map[ax, ay] += istrn + iprod
                # logging.info(('dodge', ax, ay, 'safe to stay2', istrn, pstrn_map[ax, ay]))

            else:  # Dodge this!
                # Check if it's better to just hang out
                addable = 255 - pstrn_map[ax, ay] - istrn
                if addable > istrn:
                    moveset.add_move(ax, ay, ax, ay, 0)
                    pstrn_map[ax, ay] += istrn + iprod
                    # logging.info('dodge', ax, ay, 'safe to stay3')
                    continue

                nbrs = gm.nbrs[ax, ay]

                # Find an enemy to hit!
                # Can technically lose to cap here since I skip checking pstrn
                enemy_strn = np.array([
                    gm.enemy[nnx, nny] * gm.strn[nnx, nny]
                    for (nnx, nny) in nbrs
                ])
                if enemy_strn.max() > 1:
                    dir_ = enemy_strn.argmax() + 1
                    nx, ny = nbrs[enemy_strn.argmax()]
                    moveset.add_move(ax, ay, nx, ny, dir_)
                    pstrn_map[nx, ny] += istrn
                    # logging.info(('dodge', ax, ay, 'hitting enemy at', nx, ny))
                    continue

                # Find a blank square to damage!
                # blank_strn = np.array([
                #     gm.blank[nnx, nny] * gm.strnc[nnx, nny] * (gm.strnc[nnx, nny] < istrn) *
                #     gm.safe_to_take[nnx, nny]
                #     # * (gm.dist_from_combat[nnx, nny] >= d2c)
                #     for (nnx, nny) in nbrs
                # ])

                # if blank_strn.max() > 0.5:
                #     dir_ = blank_strn.argmax() + 1
                #     nx, ny = nbrs[blank_strn.argmax()]
                #     moveset.add_move(ax, ay, nx, ny, dir_)
                #     pstrn_map[nx, ny] += istrn
                #     # logging.info(('dodge', ax, ay, 'hitting blank', nx, ny))
                #     continue

                # Find a blank square to damage!
                blank_strn = np.array([
                    gm.blank[nnx, nny] * gm.prod[nnx, nny] * (gm.strnc[nnx, nny] < istrn) *
                    gm.safe_to_take[nnx, nny]
                    # * (gm.dist_from_combat[nnx, nny] >= d2c)
                    for (nnx, nny) in nbrs
                ])

                if blank_strn.max() > 0.5:
                    dir_ = blank_strn.argmax() + 1
                    nx, ny = nbrs[blank_strn.argmax()]
                    moveset.add_move(ax, ay, nx, ny, dir_)
                    pstrn_map[nx, ny] += istrn
                    # logging.info(('dodge', ax, ay, 'hitting blank', nx, ny))
                    continue

                # # Find somewhere to fit!
                # can_fit = np.array([
                #     gm.owned[nnx, nny] * ((pstrn_map[nnx, nny] + istrn) <= strlim_cell)
                #     * gm.safe_to_take[nnx, nny]
                #     * (gm.dist_from_combat[nnx, nny] >= 1)
                #     * (1 / gm.prod[nnx, nny])
                #     for (nnx, nny) in nbrs
                # ])
                # if can_fit.max() > 0:
                #     # Need to make this favour the lower production option
                #     dir_ = can_fit.argmax() + 1
                #     nx, ny = nbrs[can_fit.argmax()]
                #     moveset.add_move(ax, ay, nx, ny, dir_)
                #     pstrn_map[nx, ny] += istrn
                #     # logging.info(('dodge', ax, ay, 'can fit in', nx, ny))
                #     continue

                # Go to the weakest remaining square
                owned_strn = np.array([
                    gm.owned[nnx, nny] * (pstrn_map[nnx, nny] + gm.strn[nnx, nny])
                    # + (gm.dist_from_combat[nnx, nny] < d2c) * 1000
                    for (nnx, nny) in nbrs
                ])
                owned_strn[owned_strn == 0] = 999

                dir_ = owned_strn.argmin() + 1
                nx, ny = nbrs[owned_strn.argmin()]
                moveset.add_move(ax, ay, nx, ny, dir_)
                pstrn_map[nx, ny] += istrn
                # logging.info(('dodge', ax, ay, 'owned strn', nx, ny))
                continue

        return moveset

    @staticmethod
    def nxny_to_cardinal(gm, x, y, nx, ny):
        dx, dy = (nx - x), (ny - y)
        if dx == gm.width - 1:
            dx = -1
        if dx == -1 * (gm.width - 1):
            dx = 1
        if dy == gm.height - 1:
            dy = -1
        if dy == -1 * (gm.height - 1):
            dy = 1

        if (dx, dy) == (0, 0):
            return 0
        elif (dx, dy) == (0, -1):
            return 1
        elif (dx, dy) == (1, 0):
            return 2
        elif (dx, dy) == (0, 1):
            return 3
        elif (dx, dy) == (-1, 0):
            return 4
        else:
            return 0
