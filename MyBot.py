import numpy as np
import dexlib.nphlt as hlt
import logging
from scipy.ndimage import maximum_filter
from scipy.ndimage.filters import gaussian_filter
from dexlib.resolver import Resolver

logging.basicConfig(filename='wtf.info', level=logging.DEBUG, filemode="w")


class Combatant:
    """Handle all the moves for combat zones."""

    def __init__(self, com_radius=8):
        self.com_radius = com_radius
        self.combat_wait = 4

    def decide_combat_moves(self, gm):
        self.moves = {}
        self.moved = np.zeros_like(gm.owned)

        com_Cs = gm.plus_filter(gm.ubrdr_combat, max) * gm.owned

        # Actually, I need a diamond filter!
        # close_Cs = maximum_filter(gm.ubrdr_combat, size=self.com_radius) * gm.owned
        # close_Cs -= com_Cs
        # Lazymode
        close_Cs = com_Cs.copy()
        for i in range(self.com_radius):
            close_Cs = np.maximum(close_Cs, gm.plus_filter(close_Cs, max))
        close_Cs -= com_Cs
        close_Cs *= gm.owned

        self.decide_melee_moves(gm, np.transpose(np.nonzero(com_Cs)))
        self.decide_close_moves(gm, np.transpose(np.nonzero(close_Cs)), com_Cs)

        return self.moved

    def decide_melee_moves(self, gm, locs):
        for cx, cy in locs:
            if gm.strnc[cx, cy] < (gm.prodc[cx, cy] * self.combat_wait):
                continue

            nbrs = gm.nbrs[(cx, cy)]
            scores = [gm.combat_heur[nx, ny] for (nx, ny) in nbrs]

            self.moves[(cx, cy)] = nbrs[np.argmax(scores)]
            self.moved[cx, cy] = True

            nx, ny = nbrs[np.argmax(scores)]
            # logging.debug(((cx, cy), 'Melee!', scores, (nx, ny),
            # gm.strn[nx, ny], gm.prod[nx, ny], gm.enemy[nx, ny], gm.blank[nx, ny]))

    def decide_close_moves(self, gm, locs, com_Cs):
        for cx, cy in locs:
            if gm.strnc[cx, cy] < (gm.prodc[cx, cy] * self.combat_wait):
                continue

            dmat = np.divide(com_Cs, gm.dists[cx, cy])
            tx, ty = np.unravel_index(dmat.argmax(), dmat.shape)

            self.moves[(cx, cy)] = tx, ty
            self.moved[cx, cy] = True
            # logging.debug(((cx, cy), 'Moving to combat!', (tx, ty)))

    def dump_moves(self, gm):
        # Can replace some of this with explicit directions
        return self.moves


class MoveMaker:
    """Evaluate the value of border squares and coordinate moves.
    Values are taken for each x, y, s, where s is the degree to which
    to hunt for teamups.
    """
    def __init__(self, gm, maxd, glob_k):
        self.maxd = maxd
        self.glob_k = glob_k
        self.bulk_mvmt_off = 10
        self.glob_invest_cap = 1.8

        # print(' '.join(['locmax', 'locmin', 'globmax', 'globmin']),
        #       file=open("vals.txt", "w"))

    def decide_noncombat_moves(self, gm, moved):
        # Masking like this isn't _quite_ right
        motile = ((gm.strnc >= gm.prodc * 4) * gm.owned).astype(bool)
        motile[np.nonzero(gm.gte_nbr)] = True
        motile[np.nonzero(moved)] = False
        strn_avail = gm.ostrn * motile

        t2r = gm.strnc / gm.prodc    # Can relax this later
        Vloc, Vglob = self.get_cell_value(gm)

        Bs = [(x, y, s) for (x, y) in gm.ubrdr_locs
              for s in range(1, min(gm.owned.sum(), self.maxd) + 1)]
        Cs = gm.owned_locs
        loc_to_Cs = {(x, y): i for i, (x, y) in enumerate(Cs)}

        m_support = np.zeros((len(Bs), len(Cs)), dtype=bool)
        mv_loc = np.zeros(len(Bs), dtype=float)
        mv_glob = np.zeros(len(Bs), dtype=float)

        # moved = np.zeros_like(gm.prod, dtype=bool)
        assigned = np.zeros_like(gm.prod, dtype=bool)

        # Calculate move values and assignments
        for i, (bx, by, s) in enumerate(Bs):
            assign_idx = np.where(gm.dists[bx, by] <= s * gm.owned)
            nbr_strn = strn_avail[assign_idx].sum()
            nbr_prod = gm.oprod[assign_idx].sum()

            bstrn = gm.strn[bx, by]

            t2c = max(s, (bstrn - nbr_strn) / nbr_prod)

            mv_loc[i] = Vloc[bx, by] / (t2c + t2r[bx, by])
            mv_glob[i] = Vglob[bx, by]
            if nbr_strn > bstrn:
                mv_glob[i] *= min(self.glob_invest_cap, np.sqrt(nbr_strn / bstrn))

            assign_locs = np.transpose(assign_idx)
            assign_is = np.fromiter((loc_to_Cs[x, y] for (x, y) in assign_locs),
                                    dtype=int)
            m_support[i, assign_is] = True

        m_values = mv_loc + mv_glob
        m_values *= -1  # Too lazy to worry about reverse iterating
        m_sorter = np.argsort(m_values)
        # bcutoff = np.median(m_values)
        bcutoff = np.percentile(m_values, 50)

        moveset = []
        for mi in m_sorter:
            # if m_values[mi] > bcutoff:
                logging.debug((Bs[mi], m_values[mi], mv_loc[mi], mv_glob[mi]))

        # logging.debug(((mv_loc.max(), mv_loc.min()), (mv_glob.max(), mv_glob.min())))
        # print(mv_loc.max(), mv_loc.min(), mv_glob.max(), mv_glob.min(),
        #       file=open("vals.txt", "a"))

        for mi in m_sorter:
            bx, by, _ = Bs[mi]
            if assigned[bx, by] or m_values[mi] == 0 or m_values[mi] > bcutoff:
                continue
            else:
                # Can do better than a max here!
                sel_cs = m_support[mi]
                m_values[np.nonzero(m_support[:, sel_cs].max(axis=1).flatten())] = 0
                moveset.append((Bs[mi], m_support[mi]))
                assigned[bx, by] = True

        self.moves = {}
        for (mx, my, s), assignment in moveset:
            for ax, ay in Cs[assignment]:
                if motile[ax, ay]:  # and s == gm.dists[ax, ay, mx, my]:
                    self.moves[(ax, ay)] = (mx, my)
                    # logging.debug(((ax, ay), 'moving on assignment'))
                moved[ax, ay] = True
                # logging.debug((motile[ax, ay], gm.strnc[ax, ay], gm.prodc[ax, ay]))
                # logging.debug(('brdr', (mx, my, s), (ax, ay)))

        # Get bulk moves now
        # to_move = np.maximum(0, motile - moved)
        to_move = motile.copy()
        to_move[np.nonzero(moved)] = False
        to_move_locs = np.transpose(np.nonzero(to_move))
        for ax, ay in to_move_locs:
            # Whatever, revisit
            prox_value = np.divide(Vloc + Vglob, gm.dists[ax, ay] + self.bulk_mvmt_off)
            tx, ty = np.unravel_index(prox_value.argmax(), prox_value.shape)
            self.moves[(ax, ay)] = tx, ty
            # logging.debug(((ax, ay), 'moving from bulk'))
            # logging.debug((motile[ax, ay], gm.strnc[ax, ay], gm.prodc[ax, ay]))
            # logging.debug(('klub', (tx, ty, gm.dists[tx, ty, ax, ay]), (ax, ay)))

    def dump_moves(self, gm):
        # Need to force corner moves, don't forget
        return self.moves

    def get_cell_value(self, gm):
        # local_value = gm.prodc * gm.ubrdr
        local_value = gaussian_filter(gm.prodc, 2, mode='wrap') * gm.ubrdr
        local_value = np.maximum(local_value, gm.prodc) * gm.ubrdr
        global_value = gm.Mbval

        return local_value, global_value * self.glob_k


game_map = hlt.ImprovedGameMap()
hlt.send_init("DexBotNeuer")
game_map.get_frame()
game_map.update()


bord_eval = MoveMaker(game_map, 10, 0.1)
combatant = Combatant(12)
resolver = Resolver(game_map)


while True:
    logging.debug('TURN ------------' + str(game_map.turn))
    game_map.update()

    moved = combatant.decide_combat_moves(game_map)
    bord_eval.decide_noncombat_moves(game_map, moved)

    comb_moves = combatant.dump_moves(game_map)
    bord_moves = bord_eval.dump_moves(game_map)
    resolved_moves = resolver.resolve({**comb_moves, **bord_moves}, game_map)

    hlt.send_frame(resolved_moves)
    game_map.get_frame()
