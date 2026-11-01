#!/usr/bin/env python3
"""Baca log tombol di host SeisComp (.7), cetak JSON untuk `manage.py backfill_seiscomp`.

Hanya membaca. Kedua tombol menulis ke log yang sama, jadi jenis klik disimpulkan:
sebelum CUTOFF hanya Send This Data yang mengirim ke website, sehingga klik tanpa
catatan kirim dalam 120 detik adalah Send QC. Klik pertama suatu event selalu dianggap
Send This Data, karena push belum ada pada awal 3 Oktober.

Antara QC_PUSH dan CUTOFF Send QC sudah mengirim tetapi belum memberi tanda stage. Di
rentang itu Send QC menulis satu baris log (--quiet) dan Send This Data dua baris. Klik
sesudah CUTOFF sudah tercatat langsung dan tidak diikutkan.
"""
import datetime as D
import glob
import json
import os
import re
import sys

START = '20261003'
QC_PUSH = D.datetime(2026, 11, 1, 9, 12, 28)  # Send QC mulai mengirim ke website
CUTOFF = D.datetime(2026, 11, 1, 9, 33, 10)   # Send QC mulai memberi tanda stage=qc
WINDOW = D.timedelta(seconds=120)
WIT = D.timezone(D.timedelta(hours=9))
HOME = os.path.expanduser('~')
END_MARK = '----------------end--------------'


def clicks():
    out = []
    for path in sorted(glob.glob(HOME + '/alarm/log/SendThisData2026*.txt')):
        day = path[-12:-4]
        if day < START:
            continue
        with open('%s/alarm/log/kirim%s.txt' % (HOME, day)) as fh:
            times = [l.split()[3] for l in fh if l.startswith('waktu awal')]
        with open(path, errors='replace') as fh:
            texts = [b.strip('\n') + '\n' for b in fh.read().split(END_MARK) if 'Public ID' in b]
        if len(times) != len(texts):
            sys.exit('log %s tidak sejajar: %d klik, %d bulletin' % (day, len(times), len(texts)))
        for stamp, text in zip(times, texts):
            when = D.datetime.strptime(stamp, '%Y%m%d%H%M%S')
            if when < CUTOFF:
                out.append((when, re.search(r'Public ID\s+(\S+)', text).group(1), text))
    return sorted(out, key=lambda c: c[0])


def pushes():
    ok, failed, doubled = [], [], set()
    for path in glob.glob(HOME + '/prg/log/ingest189_2026*.log'):
        with open(path, errors='replace') as fh:
            lines = fh.readlines()
            for line in set(lines):
                m = re.match(r'\[(\S+ \S+)\] \S+ (OK \(\w+\) (\S+)|GAGAL)', line)
                if m:
                    if lines.count(line) > 1:
                        doubled.add(m.group(1))
                    when = D.datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S')
                    (ok.append((when, m.group(3))) if m.group(3) else failed.append(when))
    return ok, failed, doubled


def main():
    ok, failed, doubled = pushes()
    events = {}
    for when, event_id, text in clicks():
        pushed = (any(when <= t <= when + WINDOW and e == event_id for t, e in ok)
                  or any(when <= t <= when + WINDOW for t in failed))
        if when >= QC_PUSH:     # Send QC ikut mengirim: bedakan dari jumlah baris log
            pushed = any(when <= t <= when + WINDOW and e == event_id
                         and t.strftime('%Y-%m-%d %H:%M:%S') in doubled for t, e in ok)
        events.setdefault(event_id, []).append((when, pushed, text))
    items = []
    for event_id, seq in events.items():
        qc = [c for c in seq[1:] if not c[1]]
        iso = lambda t: t.replace(tzinfo=WIT).isoformat()
        items.append({
            'event_id': event_id, 'clicks': len(seq),
            'first_click': iso(seq[0][0]), 'last_click': iso(seq[-1][0]),
            'last_qc': iso(qc[-1][0]) if qc else None, 'last_text': seq[-1][2],
        })
    json.dump(items, sys.stdout)


if __name__ == '__main__':
    main()
