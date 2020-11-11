import abc
import math

import matplotlib.pyplot as plt
import matplotlib.colors as colors
from matplotlib import transforms
from matplotlib.colors import LinearSegmentedColormap
from mpl_toolkits.axes_grid1.axes_divider import make_axes_locatable
import numpy as np
from scipy import ndimage

from coolbox.utilities import (
    GenomeRange,
    get_logger
)

log = get_logger(__name__)


STYLE_TRIANGULAR = 'triangular'
STYLE_MATRIX = 'matrix'
STYLE_WINDOW = 'window'

DEPTH_FULL = 'full'


JuiceBoxLikeColor = LinearSegmentedColormap.from_list(
    'interaction', ['#FFFFFF', '#FFDFDF', '#FF7575', '#FF2626', '#F70000'])
JuiceBoxLikeColor.set_bad("white")
JuiceBoxLikeColor.set_under("white")


cmaps = {
    "JuiceBoxLike": JuiceBoxLikeColor
}


class PlotHiCMatrix(abc.ABC):

    DEFAULT_COLOR = 'YlOrRd'
    SMALL_VALUE = 1e-12

    def __init__(self, *args, **kwargs):
        self.ax = None
        self.label_ax = None
        self.matrix = None
        self._out_of_bound = False

    @property
    def is_inverted(self):
        if 'orientation' in self.properties and self.properties['orientation'] == 'inverted':
            return True
        else:
            # default: not inverted
            return False

    @property
    def style(self):
        if 'style' in self.properties:
            return self.properties['style']
        else:
            # default triangular style
            return STYLE_TRIANGULAR

    @property
    def balance(self):
        if self.properties['balance'] == 'no':
            return False
        else:
            file = self.properties['file']
            from coolbox.utilities.hic.tools import file_type
            if file_type(file) == '.hic':
                if self.properties['balance'] == 'yes':
                    return 'KR'  # default use KR balance
                else:
                    return self.properties['balance']
            else:
                return True

    @property
    def is_balance(self):
        return bool(self.balance)

    @property
    def matrix_val_range(self):
        small = 1e-4
        arr = self.matrix
        arr_no_nan = arr[np.logical_not(np.isnan(arr))]
        min_, max_ = 1e-4, 1.0

        try:
            if self.properties['min_value'] == 'auto':
                # set minimal value for color bar
                min_ = arr[arr > arr.min()].min()
            else:
                min_ = self.properties['min_value']

            if self.properties['max_value'] == 'auto':
                max_ = arr_no_nan.max()
            else:
                max_ = self.properties['max_value']

            if max_ <= min_:
                max_ = min_ + small
        except ValueError as e:
            log.warning(e)
            return min_, max_

        return min_, max_

    def __get_window_matrix(self, arr):
        small = self.SMALL_VALUE
        window_matrix = ndimage.rotate(arr, 45, prefilter=False, cval=small)
        rows, cols = window_matrix.shape
        if self._out_of_bound == 'left':
            # left side out of bound
            x = cols // 3
            window_matrix = window_matrix[(rows//6):((rows//2) + 1), :(2*x+1)]
        elif self._out_of_bound == 'right':
            # right side out of bound
            x = cols // 3
            window_matrix = window_matrix[(rows//6):((rows//2) + 1), :(2*x+1)]
        elif self._out_of_bound == 'both':
            # double side out of bound
            x = cols // 3
            window_matrix = window_matrix[(rows//6):((rows//2) + 1), :]
        else:
            # normal
            x = cols // 4
            window_matrix = window_matrix[(rows//4):(rows//2 + 1), x:(3*x + 1)]

        # cut depth
        if self.properties['depth_ratio'] != 'auto' and self.properties['depth_ratio'] != DEPTH_FULL:
            depth_ratio = float(self.properties['depth_ratio'])
            depth = int(window_matrix.shape[0] * depth_ratio)
            window_matrix = window_matrix[-depth:, :]

        return window_matrix

    def __plot_matrix(self, genome_range):
        start, end = genome_range.start, genome_range.end
        ax = self.ax
        arr = self.matrix
        cm = self.properties['color']
        if isinstance(cm, str):
            if cm in cmaps:
                cmap = cmaps[cm]
            else:
                cmap = plt.get_cmap(self.properties['color'])
                lowest = cmap(0)
                cmap.set_bad(lowest)
                cmap.set_under(lowest)
        else:
            cmap = cm
        c_min, c_max = self.matrix_val_range

        if self.style == STYLE_TRIANGULAR:
            # triangular style
            scale_r = 1 / math.sqrt(2)
            r_len = end - start
            tr = transforms.Affine2D().translate(-start, -start)\
                .rotate_deg_around(0, 0, 45)\
                .scale(scale_r)\
                .translate(start+r_len/2, -r_len/2)
            img = ax.matshow(arr, cmap=cmap,
                             transform=tr+ax.transData,
                             extent=(start, end, start, end),
                             aspect='auto')
        elif self.style == STYLE_WINDOW:
            # window style
            scale_r = 2 / math.sqrt(2)
            r_len = end - start
            delta_left = start - self.fetch_region.start
            tr = transforms.Affine2D().translate(-start-delta_left, -start) \
                .rotate_deg_around(0, 0, 45) \
                .scale(scale_r) \
                .translate(start+delta_left+r_len/2, -r_len/2)
            img = ax.matshow(arr, cmap=cmap,
                             transform=tr + ax.transData,
                             extent=(start, end, start, end),
                             aspect='auto')
        else:
            # matrix style
            img = ax.matshow(arr, cmap=cmap,
                             extent=(start, end, end, start),
                             aspect='auto')

        if self.properties['norm'] == 'log':
            img.set_norm(colors.LogNorm(vmin=c_min, vmax=c_max))
        else:
            img.set_norm(colors.Normalize(vmin=c_min, vmax=c_max))

        return img

    def __adjust_figure(self, genome_range):
        ax = self.ax
        gr = genome_range
        if self.style == STYLE_TRIANGULAR or self.style == STYLE_WINDOW:

            if self.properties['depth_ratio'] == DEPTH_FULL:
                depth = gr.length / 2
            else:
                depth = (gr.length / 2) * self.properties['depth_ratio']

            if self.is_inverted:
                ax.set_ylim(depth, 0)
            else:
                ax.set_ylim(0, depth)
        else:
            ax.set_ylim(gr.end, gr.start)
        ax.set_xlim(gr.start, gr.end)

    def __plot_colorbar(self, img, orientation='vertical'):
        if orientation == 'horizontal':
            ax_divider = make_axes_locatable(self.ax)
            if self.is_inverted:
                cax = ax_divider.append_axes("top", size=0.09, pad=0.2)
            else:
                cax = ax_divider.append_axes("bottom", size=0.09, pad=0.2)
            plt.colorbar(img, cax=cax, orientation='horizontal')
        else:  # vertical
            y_ax = self.y_ax

            if self.properties['norm'] == 'log':
                from matplotlib.ticker import LogFormatter
                formatter = LogFormatter(10, labelOnlyBase=False)
                aa = np.array([1, 2, 5])
                c_min, c_max = self.matrix_val_range

                def abs_inc(num):
                    if num != 0:
                        sign = num / abs(num)
                        return int(sign * abs(num + 1))
                    else:
                        return 1

                lower_ = int(np.log10(c_min))
                upper_ = abs_inc(int(np.log10(c_max)))
                tick_values = np.concatenate([aa * 10 ** x for x in range(lower_, upper_)])

                c_bar = plt.colorbar(img, ax=y_ax, ticks=tick_values, format=formatter, fraction=0.98)
            else:
                c_bar = plt.colorbar(img, ax=y_ax, fraction=0.98)

            c_bar.solids.set_edgecolor("face")
            c_bar.ax.tick_params(labelsize='smaller')

            c_bar.ax.yaxis.set_ticks_position('left')

    def __fetch_window_matrix(self, genome_range):
        from copy import copy
        fetch_range = copy(genome_range)
        x = (genome_range.end - genome_range.start) // 2
        fetch_range.start = genome_range.start - x
        fetch_range.end = genome_range.end + x

        if fetch_range.start < 0:
            fetch_range.start = genome_range.start
            self._out_of_bound = 'left'

        try:
            arr = self.fetch_matrix(fetch_range)
        except ValueError as e:
            if self._out_of_bound == 'left':
                self._out_of_bound = 'both'
                arr = self.fetch_matrix(genome_range)
            else:
                self._out_of_bound = 'right'
                fetch_range.end = genome_range.end
                arr = self.fetch_matrix(fetch_range)
        return arr, fetch_range

    def plot(self, ax, chrom_region, start_region, end_region):
        self.ax = ax

        self._out_of_bound = False

        genome_range = GenomeRange(chrom_region, start_region, end_region)

        # fetch matrix and perform transform process
        if self.style == STYLE_WINDOW:
            arr, fetch_region = self.__fetch_window_matrix(genome_range)
            self.fetch_region = fetch_region
        else:
            arr = self.fetch_matrix(genome_range)

        self.matrix = arr

        # plot matrix
        img = self.__plot_matrix(genome_range)
        self.__adjust_figure(genome_range)

        # plot colorbar
        if self.properties['color_bar'] == 'no':
            pass
        else:
            if hasattr(self, 'y_ax') and self.properties['color_bar'] == 'vertical':
                self.__plot_colorbar(img, orientation='vertical')
            else:
                self.__plot_colorbar(img, orientation='horizontal')

        # plot label
        self.plot_label()

    def get_track_height(self, frame_width):
        """
        calculate track height dynamically.
        """
        if self.style == STYLE_TRIANGULAR:
            height = frame_width * 0.5
        elif self.style == STYLE_WINDOW:
            if 'height' in self.properties and self.properties['height'] != 'hic_auto':
                height = self.properties['height']
            else:
                height = frame_width * 0.5
        else:
            height = frame_width * 0.8

        if 'depth_ratio' in self.properties and self.properties['depth_ratio'] != DEPTH_FULL:
            if self.properties['style'] != STYLE_MATRIX:
                height = height * self.properties['depth_ratio']

        if 'color_bar' in self.properties and self.properties['color_bar'] != 'no':
            height += 1.5

        return height
