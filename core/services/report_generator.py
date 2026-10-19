"""Report generation for forensic documentation."""

import logging
import csv
import json
import hashlib
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict

from ..models.scan_result import ScanResult, ScanStatistics
from ..models.file_entry import FileEntry, FileStatus, RecoveryConfidence, FileCategory

logger = logging.getLogger(__name__)


@dataclass
class ReportMetadata:
    """Report metadata."""
    case_number: str
    examiner_name: str
    organization: str
    notes: str = ""
    evidence_id: str = ""


class ReportGenerator:
    """
    Generate forensic reports in multiple formats.
    """
    
    def __init__(self, scan_result: ScanResult, metadata: Optional[ReportMetadata] = None):
        """
        Initialize report generator.
        
        Args:
            scan_result: Scan result to report on
            metadata: Report metadata
        """
        self.scan_result = scan_result
        self.metadata = metadata or ReportMetadata(
            case_number="CASE-001",
            examiner_name="Unknown",
            organization="Unknown",
        )
        self.generated_at = datetime.now()
        
        logger.info(f"Report generator initialized for case {self.metadata.case_number}")
    
    def generate_pdf(self, output_path: Path) -> Path:
        """
        Generate PDF report.
        
        Args:
            output_path: Output file path
            
        Returns:
            Path to generated PDF
        """
        logger.info(f"Generating PDF report: {output_path}")
        
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import letter, A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch, cm
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
            from reportlab.platypus import PageBreak
            
            # Create PDF
            doc = SimpleDocTemplate(
                str(output_path),
                pagesize=A4,
                rightMargin=2*cm,
                leftMargin=2*cm,
                topMargin=2*cm,
                bottomMargin=2*cm,
            )
            
            # Container for the 'Flowable' objects
            elements = []
            
            # Styles
            styles = getSampleStyleSheet()
            styles.add(ParagraphStyle(
                name='Heading1Large',
                parent=styles['Heading1'],
                fontSize=24,
                spaceAfter=30,
                textColor=colors.HexColor('#1e1e1e'),
            ))
            styles.add(ParagraphStyle(
                name='Heading2Medium',
                parent=styles['Heading2'],
                fontSize=16,
                spaceAfter=12,
                textColor=colors.HexColor('#0078d4'),
            ))
            styles.add(ParagraphStyle(
                name='BodySmall',
                parent=styles['BodyText'],
                fontSize=10,
                spaceAfter=6,
            ))
            styles.add(ParagraphStyle(
                name='Mono',
                parent=styles['BodyText'],
                fontName='Courier',
                fontSize=9,
                spaceAfter=6,
            ))
            
            # Title
            elements.append(Paragraph("🔍 Ever Recover - Forensic Report", styles['Heading1Large']))
            elements.append(Spacer(1, 0.3*inch))
            
            # Case information
            elements.append(Paragraph("Case Information", styles['Heading2Medium']))
            case_info = [
                ["Case Number:", self.metadata.case_number],
                ["Examiner:", self.metadata.examiner_name],
                ["Organization:", self.metadata.organization],
                ["Report Generated:", self.generated_at.strftime("%Y-%m-%d %H:%M:%S")],
                ["Evidence ID:", self.metadata.evidence_id or "N/A"],
            ]
            if self.metadata.notes:
                case_info.append(["Notes:", self.metadata.notes])
            
            case_table = Table(case_info, colWidths=[2*inch, 4*inch])
            case_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            elements.append(case_table)
            elements.append(Spacer(1, 0.5*inch))
            
            # Scan summary
            elements.append(Paragraph("Scan Summary", styles['Heading2Medium']))
            stats = self.scan_result.statistics
            
            summary_data = [
                ["Device Path", self._truncate_path(self.scan_result.device.path, 50)],
                ["Device Size", self._format_size(self.scan_result.device.total_size)],
                ["Scan Duration", f"{self.scan_result.duration:.1f} seconds"],
                ["Total Files Found", str(stats.total_files)],
                ["Deleted Files", str(stats.deleted_files)],
                ["Recoverable Files", str(stats.recoverable_size)],
                ["Total Size", self._format_size(stats.total_size)],
                ["Fragmented Files", str(stats.fragmented_files)],
                ["Scan Errors", str(stats.scan_errors)],
            ]
            
            summary_table = Table(summary_data, colWidths=[2*inch, 4*inch])
            summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            elements.append(summary_table)
            elements.append(Spacer(1, 0.5*inch))
            
            # Files by category
            elements.append(Paragraph("Files by Category", styles['Heading2Medium']))
            category_data = [['Category', 'Count']]
            for cat, count in sorted(stats.files_by_category.items()):
                category_data.append([cat, str(count)])
            
            category_table = Table(category_data, colWidths=[3*inch, 2*inch])
            category_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0078d4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f8f8')]),
            ]))
            elements.append(category_table)
            elements.append(Spacer(1, 0.5*inch))
            
            # Files by confidence
            elements.append(Paragraph("Files by Confidence", styles['Heading2Medium']))
            confidence_data = [['Confidence', 'Count']]
            for conf, count in sorted(stats.files_by_confidence.items()):
                confidence_data.append([conf, str(count)])
            
            confidence_table = Table(confidence_data, colWidths=[3*inch, 2*inch])
            confidence_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0078d4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f8f8')]),
            ]))
            elements.append(confidence_table)
            elements.append(PageBreak())
            
            # File listing
            elements.append(Paragraph("File Listing", styles['Heading2Medium']))
            elements.append(Paragraph(f"Total {len(self.scan_result.files)} files found", styles['BodySmall']))
            elements.append(Spacer(1, 0.2*inch))
            
            # File table
            file_data = [['Status', 'Filename', 'Size', 'Category', 'Confidence']]
            
            # Show first 100 files
            for file_entry in self.scan_result.files[:100]:
                status_icon = self._get_status_icon(file_entry.status)
                file_data.append([
                    status_icon,
                    self._truncate_text(file_entry.display_name, 30),
                    self._format_size(file_entry.file_size),
                    file_entry.file_category.name,
                    file_entry.recovery_confidence.name,
                ])
            
            if len(self.scan_result.files) > 100:
                file_data.append([f"... and {len(self.scan_result.files) - 100} more files", "", "", "", ""])
            
            file_table = Table(file_data, colWidths=[0.5*inch, 3*inch, 1*inch, 1.5*inch, 1*inch])
            file_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0078d4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f8f8')]),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            elements.append(file_table)
            
            # Footer
            elements.append(Spacer(1, 0.5*inch))
            elements.append(Paragraph(
                f"Report generated by Ever Recover v1.0.0 | "
                f"Page 1 of 1 | {self.generated_at.strftime('%Y-%m-%d %H:%M')}",
                styles['BodySmall']
            ))
            
            # Build PDF
            doc.build(elements)
            
            logger.info(f"PDF report generated: {output_path}")
            return output_path
            
        except Exception as e:
            logger.exception(f"Error generating PDF: {e}")
            raise
    
    def generate_html(self, output_path: Path) -> Path:
        """
        Generate HTML report with interactive charts.
        
        Args:
            output_path: Output file path
            
        Returns:
            Path to generated HTML
        """
        logger.info(f"Generating HTML report: {output_path}")
        
        stats = self.scan_result.statistics
        
        # Prepare data for charts
        category_labels = list(stats.files_by_category.keys())
        category_values = list(stats.files_by_category.values())
        
        confidence_labels = list(stats.files_by_confidence.keys())
        confidence_values = list(stats.files_by_confidence.values())
        
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ever Recover - Forensic Report</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #1e1e1e 0%, #3e3e3e 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 32px;
            margin-bottom: 10px;
        }}
        .header p {{
            opacity: 0.8;
            font-size: 14px;
        }}
        .content {{
            padding: 40px;
        }}
        .section {{
            margin-bottom: 40px;
        }}
        .section h2 {{
            color: #1e1e1e;
            font-size: 24px;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #0078d4;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
            border-left: 4px solid #0078d4;
        }}
        .stat-value {{
            font-size: 32px;
            font-weight: bold;
            color: #0078d4;
        }}
        .stat-label {{
            color: #666;
            font-size: 14px;
            margin-top: 8px;
        }}
        .charts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 30px;
            margin-top: 30px;
        }}
        .chart-container {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background: #0078d4;
            color: white;
            font-weight: 600;
        }}
        tr:hover {{
            background: #f5f5f5;
        }}
        .status-icon {{
            font-size: 18px;
        }}
        .footer {{
            background: #f8f9fa;
            padding: 20px 40px;
            text-align: center;
            color: #666;
            font-size: 12px;
            border-top: 1px solid #ddd;
        }}
        .info-table {{
            width: 100%;
            margin-bottom: 20px;
        }}
        .info-table td {{
            padding: 10px;
        }}
        .info-table td:first-child {{
            font-weight: 600;
            width: 200px;
            background: #f8f9fa;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 Ever Recover - Forensic Report</h1>
            <p>Case: {self.metadata.case_number} | Examiner: {self.metadata.examiner_name}</p>
            <p>Generated: {self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        
        <div class="content">
            <div class="section">
                <h2>Case Information</h2>
                <table class="info-table">
                    <tr>
                        <td>Case Number</td>
                        <td>{self.metadata.case_number}</td>
                    </tr>
                    <tr>
                        <td>Examiner</td>
                        <td>{self.metadata.examiner_name}</td>
                    </tr>
                    <tr>
                        <td>Organization</td>
                        <td>{self.metadata.organization}</td>
                    </tr>
                    <tr>
                        <td>Evidence ID</td>
                        <td>{self.metadata.evidence_id or 'N/A'}</td>
                    </tr>
                    <tr>
                        <td>Notes</td>
                        <td>{self.metadata.notes or 'None'}</td>
                    </tr>
                </table>
            </div>
            
            <div class="section">
                <h2>Scan Summary</h2>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-value">{stats.total_files}</div>
                        <div class="stat-label">Total Files</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{stats.deleted_files}</div>
                        <div class="stat-label">Deleted Files</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{self._format_size(stats.recoverable_size)}</div>
                        <div class="stat-label">Recoverable</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{self._format_size(stats.total_size)}</div>
                        <div class="stat-label">Total Size</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{stats.fragmented_files}</div>
                        <div class="stat-label">Fragmented</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{self.scan_result.duration:.1f}s</div>
                        <div class="stat-label">Duration</div>
                    </div>
                </div>
                
                <div class="charts-grid">
                    <div class="chart-container">
                        <h3>Files by Category</h3>
                        <canvas id="categoryChart"></canvas>
                    </div>
                    <div class="chart-container">
                        <h3>Files by Confidence</h3>
                        <canvas id="confidenceChart"></canvas>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <h2>File Listing</h2>
                <p style="color: #666; margin-bottom: 15px;">
                    Showing {min(len(self.scan_result.files), 100)} of {len(self.scan_result.files)} files
                </p>
                <table>
                    <thead>
                        <tr>
                            <th>Status</th>
                            <th>Filename</th>
                            <th>Size</th>
                            <th>Category</th>
                            <th>Confidence</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join([
                            f"""<tr>
                                <td class="status-icon">{self._get_status_icon(f.status)}</td>
                                <td>{self._escape_html(f.display_name)}</td>
                                <td>{self._format_size(f.file_size)}</td>
                                <td>{f.file_category.name}</td>
                                <td>{f.recovery_confidence.name}</td>
                            </tr>"""
                            for f in self.scan_result.files[:100]
                        ])}
                    </tbody>
                </table>
            </div>
        </div>
        
        <div class="footer">
            Report generated by Ever Recover v1.0.0 | {self.generated_at.strftime('%Y-%m-%d %H:%M')}
        </div>
    </div>
    
    <script>
        // Category chart
        new Chart(document.getElementById('categoryChart'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(category_labels)},
                datasets: [{{
                    label: 'Files',
                    data: {json.dumps(category_values)},
                    backgroundColor: '#0078d4',
                    borderColor: '#005a9e',
                    borderWidth: 1
                }}]
            }},
            options: {{
                responsive: true,
                scales: {{
                    y: {{
                        beginAtZero: true,
                        ticks: {{
                            stepSize: 1
                        }}
                    }}
                }}
            }}
        }});
        
        // Confidence chart
        new Chart(document.getElementById('confidenceChart'), {{
            type: 'doughnut',
            data: {{
                labels: {json.dumps(confidence_labels)},
                datasets: [{{
                    data: {json.dumps(confidence_values)},
                    backgroundColor: ['#107c10', '#0078d4', '#ffaa00', '#c50f1f']
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{
                        position: 'bottom'
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"HTML report generated: {output_path}")
        return output_path
    
    def generate_csv(self, output_path: Path) -> Path:
        """
        Generate CSV report.
        
        Args:
            output_path: Output file path
            
        Returns:
            Path to generated CSV
        """
        logger.info(f"Generating CSV report: {output_path}")
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                'Ever Recover - Forensic Report',
                f'Case: {self.metadata.case_number}',
                f'Generated: {self.generated_at.strftime("%Y-%m-%d %H:%M:%S")}',
            ])
            writer.writerow([])
            
            # Scan statistics
            stats = self.scan_result.statistics
            writer.writerow(['Scan Statistics', '', '', ''])
            writer.writerow(['Device Path', self.scan_result.device.path])
            writer.writerow(['Device Size', self._format_size(self.scan_result.device.total_size)])
            writer.writerow(['Duration', f"{self.scan_result.duration:.1f} seconds"])
            writer.writerow([])
            writer.writerow(['Total Files', str(stats.total_files)])
            writer.writerow(['Deleted Files', str(stats.deleted_files)])
            writer.writerow(['Recoverable Files', self._format_size(stats.recoverable_size)])
            writer.writerow(['Total Size', self._format_size(stats.total_size)])
            writer.writerow(['Fragmented Files', str(stats.fragmented_files)])
            writer.writerow(['Scan Errors', str(stats.scan_errors)])
            writer.writerow([])
            
            # File listing
            writer.writerow(['File Listing', '', '', '', ''])
            writer.writerow([
                'Status',
                'Filename',
                'Size',
                'Category',
                'Confidence',
                'Offset',
                'Modified',
            ])
            
            for file_entry in self.scan_result.files:
                writer.writerow([
                    self._get_status_icon(file_entry.status),
                    file_entry.display_name,
                    self._format_size(file_entry.file_size),
                    file_entry.file_category.name,
                    file_entry.recovery_confidence.name,
                    file_entry.offset if file_entry.offset else 'N/A',
                    file_entry.modified_time.strftime('%Y-%m-%d %H:%M') if file_entry.modified_time else 'N/A',
                ])
        
        logger.info(f"CSV report generated: {output_path}")
        return output_path
    
    def generate_json(self, output_path: Path) -> Path:
        """
        Generate JSON report.
        
        Args:
            output_path: Output file path
            
        Returns:
            Path to generated JSON
        """
        logger.info(f"Generating JSON report: {output_path}")
        
        data = {
            'metadata': asdict(self.metadata),
            'generated_at': self.generated_at.isoformat(),
            'scan_result': {
                'status': self.scan_result.status if hasattr(self.scan_result, 'status') else 'unknown',
                'device_path': self.scan_result.device.path,
                'device_size': self.scan_result.device.total_size,
                'duration_seconds': self.scan_result.duration,
                'error_message': self.scan_result.error_message,
                'statistics': asdict(self.scan_result.statistics),
                'files': [
                    {
                        'file_id': f.file_id,
                        'filename': f.display_name,
                        'extension': f.extension,
                        'size': f.file_size,
                        'category': f.file_category.name,
                        'confidence': f.recovery_confidence.name,
                        'status': f.status.name,
                        'offset': f.offset,
                        'modified': f.modified_time.isoformat() if f.modified_time else None,
                    }
                    for f in self.scan_result.files
                ]
            }
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
        
        logger.info(f"JSON report generated: {output_path}")
        return output_path
    
    @staticmethod
    def _get_status_icon(status: FileStatus) -> str:
        """Get status icon."""
        icons = {
            FileStatus.EXISTING: '✅',
            FileStatus.DELETED: '🗑️',
            FileStatus.FRAGMENTED: '🧩',
            FileStatus.CORRUPTED: '⚠️',
        }
        return icons.get(status, '❓')
    
    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format size in bytes."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} PB"
    
    @staticmethod
    def _truncate_text(text: str, max_length: int) -> str:
        """Truncate text."""
        if len(text) <= max_length:
            return text
        return text[:max_length-3] + '...'
    
    @staticmethod
    def _truncate_path(path: str, max_length: int) -> str:
        """Truncate path."""
        if len(path) <= max_length:
            return path
        return '...' + path[-max_length+3:]
    
    @staticmethod
    def _escape_html(text: str) -> str:
        """Escape HTML."""
        return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
        )