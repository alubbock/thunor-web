# Class for storing and accessing HTS datasets
import pandas as pd
import numpy as np
import yaml
import os
import re


class HTS(object):

    def __init__(self, config_file, verbose=True):
        self._hts = pd.DataFrame(columns=['screen',
                                          'platefmt',
                                          'assay',
                                          'cellline',
                                          'row',
                                          'column',
                                          'drug',
                                          'dose',
                                          'time',
                                          'value'])

        # Read configuration file and set base directory
        with open(config_file, 'r') as cnf:
            self.config = yaml.load(cnf)[0]
        if verbose:
            print(self.config)
        base_dir = os.path.dirname(os.path.realpath(config_file))

        assert(len(self.config) == 1)  # Only 1 HTS expt per config file

        self._current = {'screen': self.config.keys()[0],
                         'platemaps': None,
                         'barcode': None,
                         'platefmt': None,
                         'cellline': None,
                         'numcols': None,
                         'time': None}

        # Read plate:drug map
        self._current['platemaps'] = self._read_plate_maps(
            os.path.join(base_dir,
                         self.config[self._current['screen']]['drugs'][
                             'plate_maps']),
            verbose=verbose)

        # Read plates
        plate_files = [f for f in os.listdir(base_dir) if f.endswith('.txt')]
        for plate in plate_files:
            self._read_plate(os.path.join(base_dir, plate), verbose=verbose)

        # Convert appropriate columns to numeric automatically
        self._hts = self._hts.convert_objects(convert_numeric=True)

    def _read_plate(self, plate_file, verbose=False):
        assays = self.config[self._current['screen']]['assays']
        lines_to_add = []
        with open(plate_file, 'r') as pf:
            for line in pf:
                if line.startswith('Field Group'):
                    continue
                elif line.startswith('Barcode:'):
                    self._current['barcode'] = line.split(':', 1)[1].strip()
                    self._parse_barcode()
                elif re.match('\s([0-9]+\t)+', line):
                    self._current['numcols'] = int(line.split()[-1])
                elif re.match('^[A-Z]\s', line):
                    vals = line.split(None, self._current['numcols'] + 1)
                    assay = assays[vals[-1].strip()]
                    for col in range(self._current['numcols']):
                        lines_to_add.append([self._current['screen'],
                                             self._current['platefmt'],
                                             assay,
                                             self._current['cellline'],
                                             vals[0],
                                             col + 1,
                                             self._pos_to_drug(row=vals[0],
                                                               col=col+1),
                                             self._col_to_dose(col=col+1),
                                             self._current['time'],
                                             vals[col + 1]
                                             ])
        new = pd.DataFrame(lines_to_add, columns=self._hts.columns.values)
        self._hts = pd.concat([self._hts, new])

    def _parse_barcode(self):
        m = re.match(self.config[self._current['screen']]['barcode_format'],
                     self._current['barcode'])
        self._current['cellline'] = m.group('cell_line')
        self._current['platefmt'] = m.group('plate_format')
        self._current['time'] = float(m.group('time_point'))

    def _pos_to_drug(self, row, col):
        keys = self.config[self._current['screen']]['drugs']['key']
        key = self._current['platemaps'][self._current['platefmt']].iloc[
                ord(row) - 65, col - 1]
        try:
            key = int(key)
        except ValueError:
            pass
        return keys[key]

    def _col_to_dose(self, col):
        return self.config[self._current['screen']][
            'doses'].get(int(col))

    def _read_plate_maps(self, plate_map, verbose=False):
        pm = pd.read_csv(plate_map, header=None, skip_blank_lines=False)
        map_splits = list(np.where(pm.isnull().all(axis=1))[0])
        if len(map_splits) == 0:
            if verbose:
                print '1 plate map found in %s' % plate_map
            maps = {'1': pm}
        else:
            if verbose:
                print '%d plate maps found in %s' % (len(map_splits)+1, plate_map)
            map_splits.append(pm.shape[0])
            maps = {'1': pm.iloc[0:map_splits[0], ]}
            for m in range(1, len(map_splits)):
                maps[str(m+1)] = pm.iloc[map_splits[m-1]+1:map_splits[m], ]
        return maps

    def _get_normalized_timecourses(self, screen, assay, control='DMSO'):
        # Limit ourselves to the appropriate screen and timecourse
        df = self._hts
        df = df[(df['screen'] == '16-01-18-Incyte') &
                (df['assay'] == 'Viability')]

        # Calculate control values as averages
        controls = df[(df['drug'] == control) &
                      (df['time'] == 24)].groupby([
                           'cellline',])['value'].mean().reset_index()
        # Rename column to 'control'
        controls = controls.rename(columns={'value': 'control'})
        # Merge data and control values, and calculate ratio
        df = pd.merge(df, controls, on='cellline', how='left')
        df['value_norm'] = df['value'] / df['control']

        # Calculate the mean and SD of the normalised values
        dat = df.groupby(['cellline', 'drug', 'dose', 'time'])[
            'value_norm'].agg([np.mean, np.std])


        ## @TODO: Move this to separate plots module
        import matplotlib.pyplot as plt
        import scipy as sp
        import seaborn as sns
        for _, pltdata in dat.groupby(level=[0, 1]):
            doses = pltdata.index.levels[2].values
            dose_it = iter(doses)
            colours = iter(sns.color_palette("husl", len(doses)))

            # Add control
            cell_type = pltdata.index[0][0]
            # base count 24 hrs
            # bc = controls[controls['cellline'] == cell_type][
            #     'control'].values[0]
            ctrl_counts = df[(df['cellline'] == cell_type) & (
                              df['drug'] == control)].groupby(
                                 'time')['value_norm'].agg([np.mean, np.std])

            # Plot control cdata
            t = ctrl_counts.index.get_level_values('time').values
            means = ctrl_counts['mean'].values
            sds = ctrl_counts['std'].values
            tck = sp.interpolate.splrep(t, means)
            plt.errorbar(t,
                         means,
                         yerr=sds,
                         fmt='o',
                         color='black',
                         label=control
                         )
            plt.plot(t, sp.interpolate.splev(t, tck),
                     color='black', label=None)

            for _, dosedata in pltdata.groupby(level=2):
                t = dosedata.index.get_level_values('time').values
                means = dosedata['mean'].values
                sds = dosedata['std'].values
                tck = sp.interpolate.splrep(t, means)
                col = colours.next()
                plt.errorbar(t,
                             means,
                             yerr=sds,
                             fmt='o',
                             color=col,
                             label=dose_it.next())
                plt.plot(t, sp.interpolate.splev(t, tck),
                         color=col, label=None)

            ax = plt.gca()
            box = ax.get_position()
            ax.set_position([box.x0, box.y0, box.width * 0.75, box.height])
            ax.legend(loc='center left', bbox_to_anchor=(1, 0.5))
            plt.xlim([round(min(t) - 1),
                      round(max(t) + 1)])
            plt.xlabel('Time (hrs)')

            # @TODO: Remove me
            assay = 'Viability'

            if assay == 'Viability':
                plt.ylabel('Cell growth (normalized to cell # at time zero)')
            elif assay == 'Celltox':
                plt.ylabel('Cell death (normalized to cell # at time zero)')

            drug = pltdata.index[0][1]
            plt.title(cell_type + ' / ' + drug + ' timecourse')

            fig3 = 'timecourse_' + cell_type + '_' + drug + '_' + '_' + \
                   assay + \
                   '.png'
            plt.savefig(fig3)
            plt.close()



if __name__ == '__main__':
    HTS('../screens/2016-01-18-Incyte/2016-01-18-Incyte.yml')
