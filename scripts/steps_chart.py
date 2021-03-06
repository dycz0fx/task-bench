#!/usr/bin/env python3

# Copyright 2020 Stanford University
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import argparse
import collections
import csv
import numpy
import os
import re
import sys

_columns = collections.OrderedDict([
    ('elapsed', (re.compile(r'^\s*Elapsed Time ([0-9.e+-]+) seconds$', re.MULTILINE), float)),
    ('iterations', (re.compile(r'^\s*Iterations: ([0-9]+)$', re.MULTILINE), int)),
    ('steps', (re.compile(r'^\s*Time Steps: ([0-9]+)$', re.MULTILINE), int)),
    ('tasks', (re.compile(r'^\s*Total Tasks ([0-9]+)$', re.MULTILINE), int)),
    ('flops', (re.compile(r'^\s*Total FLOPs ([0-9]+)$', re.MULTILINE), int)),
    ('bytes', (re.compile(r'^\s*Total Bytes ([0-9]+)$', re.MULTILINE), int)),
    ('width', (re.compile(r'^\s*Max Width: ([0-9]+)$', re.MULTILINE), int)),
])

def same(values):
    return all(value == values[0] for value in values)

def group_by(keys, values):
    last_key = None
    last_group = None
    for key, value in zip(keys, values):
        if key != last_key:
            if last_group is not None:
                yield (last_key, last_group)
            last_group = []
        last_key = key
        last_group.append(value)

    if last_group is not None:
        yield (last_key, last_group)

def analyze(filename, nodes, cores, threshold, peak_flops, peak_bytes):
    compute = collections.OrderedDict([
        ('time_per_task', lambda t: t['elapsed'] / t['tasks'] * nodes * cores * 1000),
    ])

    if peak_flops:
        compute['efficiency'] = lambda t: (t['flops'] / t['elapsed'] / nodes) / peak_flops
    elif peak_bytes:
        compute['efficiency'] = lambda t: (t['bytes'] / t['elapsed'] / nodes) / peak_bytes

    # Parse input columns:
    with open(filename) as f:
        text = f.read()
    table = collections.OrderedDict(
        (k, numpy.asarray([t(m.group(1)) for m in re.finditer(p, text)]))
        for k, (p, t) in _columns.items())

    # Check consistency of data:
    assert same([len(column) for column in table.values()])
    assert same(table['iterations'])
    assert same(table['width'])
    assert all(table['tasks'] == table['steps'] * table['width'])

    # Group by step count and compute statistics:
    table['steps'], table['elapsed'], table['std'], table['reps'], table['tasks'], table['flops'], table['bytes'], same_tasks, same_flops, same_bytes = list(map(
        numpy.asarray,
        zip(*[(k, numpy.mean(elapsed), numpy.std(elapsed), len(elapsed), tasks[0], flops[0], bytes[0], same(tasks), same(flops), same(bytes))
              for k, vs in group_by(table['steps'], zip(table['elapsed'], table['tasks'], table['flops'], table['bytes']))
              for elapsed, tasks, flops, bytes in [zip(*vs)]])))

    assert all(same_tasks)
    assert all(same_flops)
    assert all(same_bytes)

    for column in ('iterations', 'width'):
        table[column] = numpy.resize(table[column], table['steps'].shape)

    # Compute derived columns:
    for k, f in compute.items():
        table[k] = f(table)

    # Post-process table for output:
    for k, c in table.items():
        if any(isinstance(x, float) for x in c):
            table[k] = ['%e' % x for x in c]

    out_filename = os.path.splitext(filename)[0] + '.csv'
    with open(out_filename, 'w') as f:
        out = csv.writer(f)
        out.writerow(table.keys())
        out.writerows(zip(*list(table.values())))

def driver(inputs, summary, nodes, cores, threshold, peak_flops, peak_bytes):
    if peak_flops is not None and peak_bytes is not None:
        raise Exception('Can specify at most one --peak-* flag')
    for filename in inputs:
        analyze(filename, nodes, cores, threshold, peak_flops, peak_bytes)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('inputs', nargs='+')
    parser.add_argument('-c', '--cores', type=int, required=True)
    parser.add_argument('-n', '--nodes', type=int, required=True)
    parser.add_argument('-t', '--threshold', type=float, default=0.5)
    parser.add_argument('--peak-compute-bandwidth', type=float, default=None,
                        dest='peak_flops',
                        help='peak compute bandwidth per node in DP FLOP/s')
    parser.add_argument('--peak-memory-bandwidth', type=float, default=None,
                        dest='peak_bytes',
                        help='peak memory bandwidth per node in B/s')
    parser.add_argument('-s', '--summary')
    args = parser.parse_args()
    driver(**vars(args))
