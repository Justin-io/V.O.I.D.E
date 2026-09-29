import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import '../services/ipc_client.dart';

class ReportView extends StatefulWidget {
  final IPCClient ipc;
  final String workspacePath;

  const ReportView({super.key, required this.ipc, required this.workspacePath});

  @override
  State<ReportView> createState() => _ReportViewState();
}

class _ReportViewState extends State<ReportView> {
  String _reportContent = '';
  String _reportPath = '';
  bool _loading = false;
  StreamSubscription? _connSub;

  @override
  void initState() {
    super.initState();
    _loadReport();
    _connSub = widget.ipc.connectionStream.listen((connected) {
      if (connected && mounted && _reportContent.isEmpty) {
        _loadReport();
      }
    });
  }

  @override
  void dispose() {
    _connSub?.cancel();
    super.dispose();
  }

  Future<void> _loadReport() async {
    setState(() => _loading = true);
    try {
      final res = await widget.ipc.send('get_report');
      if (res is Map && mounted && (res['content_markdown'] != null)) {
        setState(() {
          _reportContent = res['content_markdown'] as String? ?? '';
          _reportPath = res['file_path'] as String? ?? '';
        });
      }
      if (_reportContent.isEmpty) {
        // Check latest report in workspace reports directory
        final repDir = Directory('${widget.workspacePath}/reports');
        if (repDir.existsSync()) {
          final files = repDir.listSync().whereType<File>().where((f) => f.path.endsWith('.md')).toList();
          if (files.isNotEmpty) {
            // Sort by modified time descending
            files.sort((a, b) => b.lastModifiedSync().compareTo(a.lastModifiedSync()));
            final content = files.first.readAsStringSync();
            if (mounted) {
              setState(() {
                _reportContent = content;
                _reportPath = files.first.path;
              });
            }
          }
        }
      }
    } catch (_) {}
    if (mounted) setState(() => _loading = false);
  }

  void _copyToClipboard() {
    if (_reportContent.isNotEmpty) {
      Clipboard.setData(ClipboardData(text: _reportContent));
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Engineering report copied to clipboard'),
          backgroundColor: Color(0xFF2563EB),
          duration: Duration(seconds: 2),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: const Color(0xFFF8FAFC),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_loading)
            const LinearProgressIndicator(
              minHeight: 3,
              backgroundColor: Color(0xFFE2E8F0),
              color: Color(0xFF2563EB),
            ),
          // Header Bar
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
            child: Wrap(
              alignment: WrapAlignment.spaceBetween,
              crossAxisAlignment: WrapCrossAlignment.center,
              spacing: 16,
              runSpacing: 12,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'ENGINEERING REPORT & EXPLAINABILITY',
                      style: TextStyle(
                        color: Color(0xFF64748B),
                        fontSize: 11,
                        fontWeight: FontWeight.bold,
                        letterSpacing: 1.5,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      _reportPath.isNotEmpty ? _reportPath.split('/').last : 'Executive Engineering Report',
                      style: const TextStyle(color: Color(0xFF0F172A), fontSize: 18, fontWeight: FontWeight.bold),
                    ),
                  ],
                ),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    OutlinedButton.icon(
                      onPressed: _loadReport,
                      icon: const Icon(Icons.refresh, size: 14, color: Color(0xFF475569)),
                      label: const Text('REFRESH', style: TextStyle(color: Color(0xFF475569), fontSize: 11)),
                      style: OutlinedButton.styleFrom(
                        side: const BorderSide(color: Color(0xFFCBD5E1)),
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      ),
                    ),
                    const SizedBox(width: 8),
                    ElevatedButton.icon(
                      onPressed: _reportContent.isNotEmpty ? _copyToClipboard : null,
                      icon: const Icon(Icons.copy, size: 14, color: Colors.white),
                      label: const Text('COPY MARKDOWN', style: TextStyle(color: Colors.white, fontSize: 11)),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF2563EB),
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                        elevation: 0,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const Divider(height: 1, color: Color(0xFFE2E8F0)),
          // Report Content Viewer
          Expanded(
            child: _reportContent.isEmpty
                ? const Center(
                    child: Text(
                      'No report generated yet. Click "RUN ANALYSIS" to generate full engineering report.',
                      style: TextStyle(color: Color(0xFF64748B)),
                    ),
                  )
                : SingleChildScrollView(
                    padding: const EdgeInsets.all(24),
                    child: Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(28),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(color: const Color(0xFFE2E8F0)),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withValues(alpha: 0.02),
                            blurRadius: 6,
                            offset: const Offset(0, 2),
                          ),
                        ],
                      ),
                      child: MarkdownBody(
                        data: _reportContent,
                        selectable: true,
                        shrinkWrap: true,
                        fitContent: true,
                        styleSheet: MarkdownStyleSheet(
                          p: const TextStyle(
                            color: Color(0xFF1E293B),
                            fontSize: 13,
                            height: 1.6,
                          ),
                          strong: const TextStyle(
                            fontWeight: FontWeight.w700,
                            color: Color(0xFF0F172A),
                          ),
                          em: const TextStyle(
                            fontStyle: FontStyle.italic,
                            color: Color(0xFF334155),
                          ),
                          h1: const TextStyle(
                            fontSize: 20,
                            fontWeight: FontWeight.w800,
                            color: Color(0xFF0F172A),
                            height: 1.5,
                          ),
                          h2: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                            color: Color(0xFF0F172A),
                            height: 1.4,
                          ),
                          h3: const TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w700,
                            color: Color(0xFF1E293B),
                            height: 1.4,
                          ),
                          code: const TextStyle(
                            fontFamily: 'monospace',
                            fontSize: 11.5,
                            color: Color(0xFF0F172A),
                            backgroundColor: Color(0xFFF1F5F9),
                          ),
                          codeblockDecoration: BoxDecoration(
                            color: const Color(0xFFF8FAFC),
                            borderRadius: BorderRadius.circular(4),
                            border: Border.all(color: const Color(0xFFE2E8F0)),
                          ),
                          codeblockPadding: const EdgeInsets.all(12),
                          blockquote: const TextStyle(
                            color: Color(0xFF334155),
                            fontSize: 12,
                            height: 1.5,
                          ),
                          blockquoteDecoration: BoxDecoration(
                            color: const Color(0xFFF8FAFC),
                            borderRadius: const BorderRadius.horizontal(right: Radius.circular(4)),
                            border: const Border(
                              left: BorderSide(color: Color(0xFF2563EB), width: 3),
                            ),
                          ),
                          blockquotePadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                          tableHead: const TextStyle(
                            fontWeight: FontWeight.w700,
                            color: Color(0xFF0F172A),
                            fontSize: 12,
                          ),
                          tableBody: const TextStyle(
                            color: Color(0xFF334155),
                            fontSize: 11.5,
                          ),
                          tableHeadAlign: TextAlign.left,
                          tableBorder: TableBorder.all(
                            color: const Color(0xFFCBD5E1),
                            width: 1,
                          ),
                          tableCellsPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                          tableCellsDecoration: const BoxDecoration(
                            color: Colors.white,
                          ),
                          tableColumnWidth: const FlexColumnWidth(),
                          tableScrollbarThumbVisibility: true,
                          listBullet: const TextStyle(
                            color: Color(0xFF2563EB),
                            fontWeight: FontWeight.bold,
                            fontSize: 13,
                          ),
                          horizontalRuleDecoration: BoxDecoration(
                            border: Border(
                              top: BorderSide(color: const Color(0xFFE2E8F0), width: 1),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}
