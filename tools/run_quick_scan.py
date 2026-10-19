import os
import sys
from pathlib import Path

# Add project path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard_main import RecoveryScanner

if __name__ == '__main__':
    scanner = RecoveryScanner()
    settings = {
        'source_path': os.path.join(os.path.expanduser('~'), 'Desktop'),
        'timeline_scan': True,
        'scan_mode': 'Quick Scan',
        'scan_profile': 'Forensic Analysis',
        'scan_type': 'Hybrid',
        'filesystem': 'Auto Detect',
    }
    print('Running quick folder scan on Desktop...')
    result, records, summary = scanner._scan_folder(settings['source_path'], settings)
    print('Summary:')
    print(summary)
    print(f'Records: {len(records)} files found')
    if records:
        print('First 5:')
        for r in records[:5]:
            print('-', r['name'], r['type'], r['size'])
