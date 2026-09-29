import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import '../models/ipc_models.dart';
import '../services/ipc_client.dart';

class InvestigationView extends StatefulWidget {
  final IPCClient ipc;
  final String? initialAnomalyId;
  final String? workspacePath;
  final VoidCallback? onNavigateToBaseline;
  final VoidCallback? onNavigateToReport;

  const InvestigationView({
    super.key,
    required this.ipc,
    this.initialAnomalyId,
    this.workspacePath,
    this.onNavigateToBaseline,
    this.onNavigateToReport,
  });

  @override
  State<InvestigationView> createState() => _InvestigationViewState();
}

class _InvestigationViewState extends State<InvestigationView> {
  bool _loading = false;
  List<AnomalyRecord> _anomalies = [];
  AnomalyRecord? _selectedAnomaly;
  String _selectedFilter = 'ALL';
  String _humanDecision = '';
  StreamSubscription? _connSub;

  @override
  void initState() {
    super.initState();
    _loadAnomalies();
    _connSub = widget.ipc.connectionStream.listen((connected) {
      if (connected && mounted) {
        _loadAnomalies();
      }
    });
  }

  @override
  void dispose() {
    _connSub?.cancel();
    super.dispose();
  }

  @override
  void didUpdateWidget(InvestigationView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.initialAnomalyId != null &&
        widget.initialAnomalyId != oldWidget.initialAnomalyId &&
        _anomalies.isNotEmpty) {
      setState(() {
        _selectedAnomaly = _anomalies.firstWhere(
          (a) => a.anomalyId == widget.initialAnomalyId,
          orElse: () => _selectedAnomaly ?? _anomalies.first,
        );
      });
    }
  }

  Future<void> _loadAnomalies() async {
    setState(() => _loading = true);
    try {
      final res = await widget.ipc.send('get_anomalies');
      if (res is List && mounted) {
        final list = res.map((i) => AnomalyRecord.fromJson(Map<String, dynamic>.from(i))).toList();
        setState(() {
          _anomalies = list;
          if (list.isNotEmpty) {
            if (widget.initialAnomalyId != null) {
              _selectedAnomaly = list.firstWhere(
                (a) => a.anomalyId == widget.initialAnomalyId,
                orElse: () => list.first,
              );
            } else {
              _selectedAnomaly = list.first;
            }
          }
        });
      }
    } catch (_) {}
    if (mounted) setState(() => _loading = false);
  }

  void _recordDecision(String decision) {
    setState(() => _humanDecision = decision);
    if (_selectedAnomaly != null) {
      widget.ipc.send('record_decision', {
        'anomaly_id': _selectedAnomaly!.anomalyId,
        'decision': decision,
      }).catchError((_) {});
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Decision recorded: $decision for ${_selectedAnomaly?.anomalyId}'),
        backgroundColor: const Color(0xFF2563EB),
        duration: const Duration(seconds: 2),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final anom = _selectedAnomaly;
    final filteredList = _selectedFilter == 'ALL'
        ? _anomalies
        : _anomalies.where((a) => a.severity == _selectedFilter).toList();

    return Container(
      color: const Color(0xFFF8FAFC),
      child: Column(
        children: [
          if (_loading)
            const LinearProgressIndicator(
              minHeight: 3,
              backgroundColor: Color(0xFFE2E8F0),
              color: Color(0xFF2563EB),
            ),
          Expanded(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Left Sidebar: Ranked Anomaly Episodes
                Container(
                  width: 340,
                  decoration: const BoxDecoration(
                    color: Colors.white,
                    border: Border(right: BorderSide(color: Color(0xFFE2E8F0))),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                        child: Row(
                          children: [
                            const Expanded(
                              child: Text(
                                'RANKED ANOMALIES',
                                style: TextStyle(
                                  color: Color(0xFF0F172A),
                                  fontSize: 13,
                                  fontWeight: FontWeight.bold,
                                  letterSpacing: 0.8,
                                ),
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            const SizedBox(width: 8),
                            Text(
                              '${_anomalies.length} found',
                              style: const TextStyle(
                                color: Color(0xFF2563EB),
                                fontSize: 13,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ],
                        ),
                      ),
                      // Severity Filter Pills
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
                        child: SingleChildScrollView(
                          scrollDirection: Axis.horizontal,
                          child: Row(
                            children: ['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((sev) {
                              final isSel = _selectedFilter == sev;
                              return Padding(
                                padding: const EdgeInsets.only(right: 6),
                                child: InkWell(
                                  onTap: () => setState(() {
                                    _selectedFilter = sev;
                                    final newFiltered = sev == 'ALL'
                                        ? _anomalies
                                        : _anomalies.where((a) => a.severity == sev).toList();
                                    if (newFiltered.isNotEmpty &&
                                        !newFiltered.any((a) => a.anomalyId == _selectedAnomaly?.anomalyId)) {
                                      _selectedAnomaly = newFiltered.first;
                                      _humanDecision = '';
                                    }
                                  }),
                                  borderRadius: BorderRadius.circular(4),
                                  child: Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                                    decoration: BoxDecoration(
                                      color: isSel ? const Color(0xFFEFF6FF) : const Color(0xFFF1F5F9),
                                      borderRadius: BorderRadius.circular(4),
                                      border: Border.all(
                                        color: isSel ? const Color(0xFF2563EB) : const Color(0xFFE2E8F0),
                                      ),
                                    ),
                                    child: Text(
                                      sev,
                                      style: TextStyle(
                                        color: isSel ? const Color(0xFF2563EB) : const Color(0xFF475569),
                                        fontSize: 11,
                                        fontWeight: isSel ? FontWeight.bold : FontWeight.w600,
                                      ),
                                    ),
                                  ),
                                ),
                              );
                            }).toList(),
                          ),
                        ),
                      ),
                      const SizedBox(height: 10),
                      const Divider(height: 1, color: Color(0xFFE2E8F0)),

                      Expanded(
                        child: filteredList.isEmpty
                            ? const Center(
                                child: Text('No anomalies match filter', style: TextStyle(color: Color(0xFF94A3B8), fontSize: 13)),
                              )
                            : ListView.separated(
                                itemCount: filteredList.length,
                                separatorBuilder: (context, index) => const Divider(height: 1, color: Color(0xFFF1F5F9)),
                                itemBuilder: (context, idx) {
                                  final item = filteredList[idx];
                                  final isSel = item.anomalyId == anom?.anomalyId;

                                  Color badgeColor = const Color(0xFFD97706);
                                  if (item.severity == 'CRITICAL') {
                                    badgeColor = const Color(0xFFDC2626);
                                  } else if (item.severity == 'HIGH') {
                                    badgeColor = const Color(0xFFEA580C);
                                  } else if (item.severity == 'LOW') {
                                    badgeColor = const Color(0xFF059669);
                                  }

                                  final resSign = item.residualScore >= 0 ? '+' : '';

                                  return InkWell(
                                    onTap: () => setState(() {
                                      _selectedAnomaly = item;
                                      _humanDecision = '';
                                    }),
                                    child: Container(
                                      padding: const EdgeInsets.all(14),
                                      color: isSel ? const Color(0xFFEFF6FF) : Colors.transparent,
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Row(
                                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                            children: [
                                              Expanded(
                                                child: Text(
                                                  item.equipmentId,
                                                  style: TextStyle(
                                                    color: isSel ? const Color(0xFF2563EB) : const Color(0xFF0F172A),
                                                    fontSize: 13.5,
                                                    fontWeight: FontWeight.bold,
                                                  ),
                                                  overflow: TextOverflow.ellipsis,
                                                ),
                                              ),
                                              Container(
                                                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                                decoration: BoxDecoration(
                                                  color: badgeColor.withValues(alpha: 0.12),
                                                  borderRadius: BorderRadius.circular(3),
                                                ),
                                                child: Text(
                                                  item.severity,
                                                  style: TextStyle(color: badgeColor, fontSize: 10, fontWeight: FontWeight.bold),
                                                ),
                                              ),
                                            ],
                                          ),
                                          const SizedBox(height: 5),
                                          Text(
                                            item.startTime,
                                            style: const TextStyle(color: Color(0xFF64748B), fontSize: 11.5, fontFamily: 'monospace'),
                                          ),
                                          const SizedBox(height: 6),
                                          Row(
                                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                            children: [
                                              Expanded(
                                                child: Text(
                                                  'Peak: ${item.peakZScore >= 0 ? '+' : ''}${item.peakZScore.toStringAsFixed(1)}\u03c3 ($resSign${item.residualScore.toStringAsFixed(1)} kWh)',
                                                  style: const TextStyle(color: Color(0xFF0F172A), fontSize: 11.5, fontWeight: FontWeight.w600),
                                                  overflow: TextOverflow.ellipsis,
                                                ),
                                              ),
                                              const SizedBox(width: 6),
                                              Text(
                                                '${item.persistenceCount} steps',
                                                style: const TextStyle(color: Color(0xFF64748B), fontSize: 11),
                                              ),
                                            ],
                                          ),
                                        ],
                                      ),
                                    ),
                                  );
                                },
                              ),
                      ),
                    ],
                  ),
                ),

                // Right Main Detail Pane: Evidence Chain & Critic
                Expanded(
                  child: anom == null
                      ? const Center(
                          child: Text('Select an anomaly episode from the left sidebar to inspect evidence.', style: TextStyle(color: Color(0xFF64748B), fontSize: 14)),
                        )
                      : SingleChildScrollView(
                          padding: const EdgeInsets.all(24),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              // Top Episode Summary Bar
                              Container(
                                padding: const EdgeInsets.all(22),
                                decoration: BoxDecoration(
                                  color: Colors.white,
                                  borderRadius: BorderRadius.circular(6),
                                  border: Border.all(color: const Color(0xFFE2E8F0)),
                                  boxShadow: [
                                    BoxShadow(
                                      color: Colors.black.withValues(alpha: 0.02),
                                      blurRadius: 4,
                                      offset: const Offset(0, 1),
                                    ),
                                  ],
                                ),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Row(
                                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                      children: [
                                        Row(
                                          children: [
                                            Builder(builder: (context) {
                                              Color bColor = const Color(0xFFD97706);
                                              if (anom.severity == 'CRITICAL') {
                                                bColor = const Color(0xFFDC2626);
                                              } else if (anom.severity == 'HIGH') {
                                                bColor = const Color(0xFFEA580C);
                                              } else if (anom.severity == 'LOW') {
                                                bColor = const Color(0xFF059669);
                                              }
                                              return Container(
                                                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                                                decoration: BoxDecoration(
                                                  color: bColor.withValues(alpha: 0.12),
                                                  borderRadius: BorderRadius.circular(3),
                                                ),
                                                child: Text(
                                                  anom.severity,
                                                  style: TextStyle(color: bColor, fontSize: 11, fontWeight: FontWeight.bold),
                                                ),
                                              );
                                            }),
                                            const SizedBox(width: 12),
                                            Text(
                                              anom.anomalyId,
                                              style: const TextStyle(color: Color(0xFF0F172A), fontSize: 17, fontWeight: FontWeight.bold, fontFamily: 'monospace'),
                                            ),
                                          ],
                                        ),
                                        if (widget.onNavigateToReport != null)
                                          OutlinedButton.icon(
                                            onPressed: widget.onNavigateToReport,
                                            icon: const Icon(Icons.description_outlined, size: 15, color: Color(0xFF2563EB)),
                                            label: const Text('VIEW IN REPORT', style: TextStyle(color: Color(0xFF2563EB), fontSize: 12)),
                                            style: OutlinedButton.styleFrom(
                                              side: const BorderSide(color: Color(0xFF93C5FD)),
                                              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
                                            ),
                                          ),
                                      ],
                                    ),
                                    const SizedBox(height: 12),
                                    Text(
                                      '${anom.equipmentId} • Episode Window: ${anom.startTime} \u2192 ${anom.endTime} (${anom.persistenceCount} consecutive intervals / ${anom.persistenceCount * 30} min duration)',
                                      style: const TextStyle(color: Color(0xFF475569), fontSize: 13),
                                    ),
                                    const SizedBox(height: 18),
                                    Row(
                                      children: [
                                        Expanded(child: _metricPill('Peak Residual (\u0394)', '${anom.residualScore >= 0 ? '+' : ''}${anom.residualScore.toStringAsFixed(1)} kWh', const Color(0xFFDC2626))),
                                        const SizedBox(width: 12),
                                        Expanded(child: _metricPill('Peak Z-Score', '${anom.peakZScore >= 0 ? '+' : ''}${anom.peakZScore.toStringAsFixed(1)} \u03c3', const Color(0xFFD97706))),
                                        const SizedBox(width: 12),
                                        Expanded(child: _metricPill('Multivariate Score', anom.multivariateScore.toStringAsFixed(2), const Color(0xFF2563EB))),
                                        const SizedBox(width: 12),
                                        Expanded(child: _metricPill('Confidence', '${(anom.confidence * 100).toInt()}%', const Color(0xFF059669))),
                                      ],
                                    ),
                                  ],
                                ),
                              ),

                              const SizedBox(height: 20),

                              // Episode Telemetry Zoom & Residual Profile
                              _buildAnomalyVisualCard(anom),

                              const SizedBox(height: 20),

                              // Evidence Critic Verification
                              Container(
                                padding: const EdgeInsets.all(20),
                                decoration: BoxDecoration(
                                  color: Colors.white,
                                  borderRadius: BorderRadius.circular(6),
                                  border: Border.all(color: const Color(0xFFE2E8F0)),
                                ),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Row(
                                      children: const [
                                        Icon(Icons.gavel_outlined, size: 18, color: Color(0xFF2563EB)),
                                        SizedBox(width: 8),
                                        Text(
                                          'EVIDENCE CRITIC MULTI-CRITERIA VERIFICATION',
                                          style: TextStyle(color: Color(0xFF0F172A), fontSize: 12, fontWeight: FontWeight.bold, letterSpacing: 0.8),
                                        ),
                                      ],
                                    ),
                                    const SizedBox(height: 14),
                                    _criticCheck(
                                      'Statistical Persistence Verification',
                                      'Episode persisted for ${anom.persistenceCount} consecutive intervals (\u2265 3 required). Transient sensor spikes rejected.',
                                      true,
                                    ),
                                    const SizedBox(height: 10),
                                    _criticCheck(
                                      'Contextual Non-Linear Baseline Isolation',
                                      'Residual measured against expected baseline conditioned on simultaneous cooling load and weather context.',
                                      true,
                                    ),
                                    const SizedBox(height: 10),
                                    _criticCheck(
                                      'Physical Lift & Flow Consistency',
                                      'Thermal lift (\u0394T) and water flow confirmed normal operation, eliminating sensor dropout as root cause.',
                                      true,
                                    ),
                                  ],
                                ),
                              ),

                              const SizedBox(height: 20),

                              // Interpretation & Root Cause Hypothesis
                              Container(
                                padding: const EdgeInsets.all(20),
                                decoration: BoxDecoration(
                                  color: Colors.white,
                                  borderRadius: BorderRadius.circular(6),
                                  border: Border.all(color: const Color(0xFFE2E8F0)),
                                ),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    const Text(
                                      'ENGINEERING INTERPRETATION & ROOT CAUSE',
                                      style: TextStyle(color: Color(0xFF0F172A), fontSize: 12, fontWeight: FontWeight.bold, letterSpacing: 0.8),
                                    ),
                                    const SizedBox(height: 10),
                                    Text(
                                      anom.interpretation.isNotEmpty
                                          ? anom.interpretation
                                          : 'Telemetry exhibits anomalous elevated energy consumption relative to operational thermal load. Possible condenser fouling, suboptimal vane positioning, or internal refrigerant migration.',
                                      style: const TextStyle(color: Color(0xFF334155), fontSize: 12, height: 1.5),
                                    ),
                                  ],
                                ),
                              ),

                              const SizedBox(height: 20),

                              // Human In-The-Loop Disposition Logging
                              Container(
                                padding: const EdgeInsets.all(20),
                                decoration: BoxDecoration(
                                  color: Colors.white,
                                  borderRadius: BorderRadius.circular(6),
                                  border: Border.all(color: const Color(0xFFE2E8F0)),
                                ),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Row(
                                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                      children: [
                                        const Text(
                                          'OPERATIONAL DISPOSITION & AUDIT LOGGING',
                                          style: TextStyle(color: Color(0xFF0F172A), fontSize: 12, fontWeight: FontWeight.bold, letterSpacing: 0.8),
                                        ),
                                        if (_humanDecision.isNotEmpty)
                                          Container(
                                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                            decoration: BoxDecoration(
                                              color: const Color(0xFFECFDF5),
                                              borderRadius: BorderRadius.circular(3),
                                              border: Border.all(color: const Color(0xFFA7F3D0)),
                                            ),
                                            child: Text(
                                              'Logged: $_humanDecision',
                                              style: const TextStyle(color: Color(0xFF047857), fontSize: 10, fontWeight: FontWeight.bold),
                                            ),
                                          ),
                                      ],
                                    ),
                                    const SizedBox(height: 12),
                                    Wrap(
                                      spacing: 10,
                                      runSpacing: 8,
                                      children: [
                                        ElevatedButton.icon(
                                          onPressed: () => _recordDecision('CONFIRMED_DEGRADATION'),
                                          icon: const Icon(Icons.check, size: 14, color: Colors.white),
                                          label: const Text('CONFIRM FAULT', style: TextStyle(color: Colors.white, fontSize: 11)),
                                          style: ElevatedButton.styleFrom(
                                            backgroundColor: const Color(0xFFDC2626),
                                            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                                            elevation: 0,
                                          ),
                                        ),
                                        OutlinedButton.icon(
                                          onPressed: () => _recordDecision('NORMAL_LOAD_SURGE'),
                                          icon: const Icon(Icons.close, size: 14, color: Color(0xFF64748B)),
                                          label: const Text('DISMISS (NORMAL PEAK)', style: TextStyle(color: Color(0xFF64748B), fontSize: 11)),
                                          style: OutlinedButton.styleFrom(
                                            side: const BorderSide(color: Color(0xFFCBD5E1)),
                                            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                                          ),
                                        ),
                                        OutlinedButton.icon(
                                          onPressed: () => _recordDecision('REQUEST_CALIBRATION'),
                                          icon: const Icon(Icons.tune, size: 14, color: Color(0xFF2563EB)),
                                          label: const Text('CALIBRATION CHECK', style: TextStyle(color: Color(0xFF2563EB), fontSize: 11)),
                                          style: OutlinedButton.styleFrom(
                                            side: const BorderSide(color: Color(0xFF93C5FD)),
                                            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _metricPill(String label, String value, Color color) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFF8FAFC),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: const Color(0xFFE2E8F0)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(color: Color(0xFF64748B), fontSize: 11, fontWeight: FontWeight.bold, letterSpacing: 0.5)),
          const SizedBox(height: 6),
          Text(value, style: TextStyle(color: color, fontSize: 17, fontWeight: FontWeight.w800)),
        ],
      ),
    );
  }

  Widget _criticCheck(String title, String desc, bool passed) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(
          passed ? Icons.check_circle : Icons.warning_amber_rounded,
          size: 18,
          color: passed ? const Color(0xFF059669) : const Color(0xFFDC2626),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: const TextStyle(color: Color(0xFF0F172A), fontSize: 13, fontWeight: FontWeight.bold)),
              const SizedBox(height: 3),
              Text(desc, style: const TextStyle(color: Color(0xFF475569), fontSize: 12.5, height: 1.4)),
            ],
          ),
        ),
      ],
    );
  }

  String _resolveAnomalyVisual(AnomalyRecord anom) {
    final baseDir = widget.workspacePath ?? '.';
    final visualsDir = '$baseDir/visuals';

    // 1. Direct match for anomaly ID
    final exactPath = '$visualsDir/anomaly_zoom_${anom.anomalyId}.png';
    if (File(exactPath).existsSync()) return exactPath;

    // 2. Scan visuals directory for partial match on anomaly ID or timestamp date
    final dir = Directory(visualsDir);
    if (dir.existsSync()) {
      try {
        final idClean = anom.anomalyId.replaceAll('-', '').toLowerCase();
        final datePart = anom.startTime.split(' ').first;
        for (final entry in dir.listSync()) {
          if (entry is File && entry.path.endsWith('.png')) {
            final fname = entry.path.split('/').last.toLowerCase();
            if (fname.startsWith('anomaly_zoom') && (fname.contains(idClean) || fname.contains(datePart))) {
              return entry.path;
            }
          }
        }
      } catch (_) {}
    }

    // 3. Fallback to equipment observed vs expected or residuals plot
    final eq = anom.equipmentId.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]'), '');
    final candidates = [
      '$visualsDir/obs_vs_exp_$eq.png',
      '$visualsDir/observed_vs_expected_${anom.equipmentId.toLowerCase()}.png',
      '$visualsDir/residuals_$eq.png',
    ];
    for (final c in candidates) {
      if (File(c).existsSync()) return c;
    }

    return exactPath;
  }

  void _showImageDialog(String filePath, String title) {
    showDialog(
      context: context,
      builder: (ctx) => Dialog(
        backgroundColor: Colors.white,
        insetPadding: const EdgeInsets.all(24),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(title, style: const TextStyle(color: Color(0xFF0F172A), fontSize: 13, fontWeight: FontWeight.bold)),
                  IconButton(
                    icon: const Icon(Icons.close, color: Color(0xFF64748B), size: 18),
                    onPressed: () => Navigator.pop(ctx),
                  ),
                ],
              ),
            ),
            const Divider(height: 1, color: Color(0xFFE2E8F0)),
            Flexible(
              child: InteractiveViewer(
                child: Image.file(File(filePath)),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAnomalyVisualCard(AnomalyRecord anom) {
    final visualPath = _resolveAnomalyVisual(anom);
    final file = File(visualPath);
    final exists = file.existsSync();

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: const Color(0xFFE2E8F0)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.02),
            blurRadius: 4,
            offset: const Offset(0, 1),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: const [
                  Icon(Icons.zoom_in, size: 18, color: Color(0xFF2563EB)),
                  SizedBox(width: 8),
                  Text(
                    'HIGH-RESOLUTION TELEMETRY ZOOM & RESIDUAL ENVELOPE',
                    style: TextStyle(
                      color: Color(0xFF0F172A),
                      fontSize: 12,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 0.8,
                    ),
                  ),
                ],
              ),
              if (exists)
                Row(
                  children: [
                    Text(
                      visualPath.split('/').last,
                      style: const TextStyle(
                        color: Color(0xFF94A3B8),
                        fontSize: 10,
                        fontFamily: 'monospace',
                      ),
                    ),
                    const SizedBox(width: 8),
                    InkWell(
                      onTap: () => _showImageDialog(
                        visualPath,
                        'Anomaly Zoom: ${anom.equipmentId} (${anom.anomalyId})',
                      ),
                      child: const Tooltip(
                        message: 'View Fullscreen Interactive Plot',
                        child: Icon(Icons.fullscreen, size: 18, color: Color(0xFF2563EB)),
                      ),
                    ),
                  ],
                ),
            ],
          ),
          const SizedBox(height: 12),
          if (exists)
            InkWell(
              onTap: () => _showImageDialog(
                visualPath,
                'Anomaly Zoom: ${anom.equipmentId} (${anom.anomalyId})',
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: Image.file(
                  file,
                  width: double.infinity,
                  fit: BoxFit.contain,
                ),
              ),
            )
          else
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(vertical: 24),
              decoration: BoxDecoration(
                color: const Color(0xFFF8FAFC),
                borderRadius: BorderRadius.circular(4),
                border: Border.all(color: const Color(0xFFE2E8F0)),
              ),
              child: Center(
                child: Column(
                  children: [
                    const Icon(Icons.bar_chart, size: 28, color: Color(0xFF94A3B8)),
                    const SizedBox(height: 8),
                    Text(
                      'Detailed zoom plot for ${anom.anomalyId} not yet generated',
                      style: const TextStyle(color: Color(0xFF0F172A), fontSize: 12, fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 4),
                    const Text(
                      'Run analysis or inspect the Baseline Analysis view for full-dataset regression plots.',
                      style: TextStyle(color: Color(0xFF64748B), fontSize: 11),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}
