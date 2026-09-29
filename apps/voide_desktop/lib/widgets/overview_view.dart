import 'dart:async';
import 'package:flutter/material.dart';
import '../models/ipc_models.dart';
import '../services/ipc_client.dart';
import 'anomaly_dashboard.dart';

class OverviewView extends StatefulWidget {
  final IPCClient ipc;
  final String selectedDataset;
  final VoidCallback onInvestigate;
  final VoidCallback onViewReport;
  final Function(String equipmentId)? onSelectEquipment;
  final Function(String anomalyId)? onSelectAnomaly;
  final VoidCallback? onNavigateToData;
  final VoidCallback? onNavigateToBaseline;
  final VoidCallback? onNavigateToVisuals;
  final VoidCallback? onRunPipeline;
  final bool isPipelineRunning;
  final String pipelineStage;
  final double pipelineProgress;

  const OverviewView({
    super.key,
    required this.ipc,
    this.selectedDataset = 'development_dataset.csv',
    required this.onInvestigate,
    required this.onViewReport,
    this.onSelectEquipment,
    this.onSelectAnomaly,
    this.onNavigateToData,
    this.onNavigateToBaseline,
    this.onNavigateToVisuals,
    this.onRunPipeline,
    this.isPipelineRunning = false,
    this.pipelineStage = '',
    this.pipelineProgress = 0.0,
  });

  @override
  State<OverviewView> createState() => _OverviewViewState();
}

class _OverviewViewState extends State<OverviewView> {
  bool _loading = false;
  Map<String, dynamic>? _analysisData;
  List<AnomalyRecord> _anomalies = [];
  DataProfile? _profile;
  StreamSubscription? _connSub;

  @override
  void initState() {
    super.initState();
    _loadLatestData();
    _connSub = widget.ipc.connectionStream.listen((connected) {
      if (connected && mounted) {
        _loadLatestData();
      }
    });
  }

  @override
  void dispose() {
    _connSub?.cancel();
    super.dispose();
  }

  @override
  void didUpdateWidget(OverviewView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.selectedDataset != widget.selectedDataset ||
        (oldWidget.isPipelineRunning && !widget.isPipelineRunning)) {
      _loadLatestData();
    }
  }

  Future<void> _loadLatestData() async {
    setState(() => _loading = true);
    try {
      final latest = await widget.ipc.send('get_latest_analysis');
      if (latest is Map && mounted) {
        setState(() {
          _analysisData = Map<String, dynamic>.from(latest);
          final rawAnoms = latest['anomalies'] as List?;
          if (rawAnoms != null) {
            _anomalies = rawAnoms
                .map((a) => AnomalyRecord.fromJson(Map<String, dynamic>.from(a)))
                .toList();
          }
        });
      }

      // Also get dataset profile for health score and entity counts
      final prof = await widget.ipc.send('dataset_profile', {'path': widget.selectedDataset});
      if (prof is Map && mounted) {
        setState(() {
          _profile = DataProfile.fromJson(Map<String, dynamic>.from(prof));
        });
      }
    } catch (_) {}
    if (mounted) setState(() => _loading = false);
  }

  @override
  Widget build(BuildContext context) {
    final analysis = _analysisData?['analysis'] as Map<String, dynamic>?;
    final totalRows = analysis?['row_count'] ?? _profile?.rowCount ?? 0;
    final healthScore = analysis?['data_health_score'] ?? _profile?.dataHealthScore ?? 100.0;
    final modelR2 = (analysis?['model_r2'] as num?)?.toDouble() ?? 0.0;
    final modelMetrics = analysis?['model_metrics'] as Map<String, dynamic>? ?? {};
    final entityModels = modelMetrics['entities'] as Map<String, dynamic>? ?? {};
    final rawEntities = (analysis?['entities'] as List?)?.map((e) => e.toString()).toList() ?? [];
    final entities = rawEntities.isNotEmpty
        ? rawEntities
        : (_profile?.entities.isNotEmpty == true
            ? _profile!.entities
            : entityModels.keys.toList());

    // Group anomalies by equipment
    final Map<String, List<AnomalyRecord>> anomaliesByEntity = {};
    for (final a in _anomalies) {
      anomaliesByEntity.putIfAbsent(a.equipmentId, () => []).add(a);
    }

    final topAnomaly = _anomalies.isNotEmpty ? _anomalies.first : null;

    return Container(
      color: const Color(0xFFF8FAFC),
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (_loading || widget.isPipelineRunning) ...[
              LinearProgressIndicator(
                value: widget.isPipelineRunning ? widget.pipelineProgress : null,
                minHeight: 3,
                backgroundColor: const Color(0xFFE2E8F0),
                color: const Color(0xFF2563EB),
              ),
              const SizedBox(height: 16),
            ],

            // Top Header Bar
            Wrap(
              alignment: WrapAlignment.spaceBetween,
              crossAxisAlignment: WrapCrossAlignment.center,
              spacing: 16,
              runSpacing: 12,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'ENGINEERING DATA INTELLIGENCE',
                      style: TextStyle(
                        color: Color(0xFF64748B),
                        fontSize: 11,
                        letterSpacing: 1.5,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 4),
                    const Text(
                      'Facility Chiller Anomaly & Evidence Workstation',
                      style: TextStyle(
                        color: Color(0xFF0F172A),
                        fontSize: 20,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      'Target Dataset: ${widget.selectedDataset} • ASHRAE Guideline 14 Contextual Energy Baselines',
                      style: const TextStyle(
                        color: Color(0xFF64748B),
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),

                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    OutlinedButton.icon(
                      onPressed: _loadLatestData,
                      icon: const Icon(Icons.refresh, size: 14, color: Color(0xFF475569)),
                      label: const Text('REFRESH', style: TextStyle(color: Color(0xFF475569), fontSize: 11)),
                      style: OutlinedButton.styleFrom(
                        side: const BorderSide(color: Color(0xFFCBD5E1)),
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                      ),
                    ),
                    const SizedBox(width: 8),
                    ElevatedButton.icon(
                      onPressed: widget.isPipelineRunning ? null : (widget.onRunPipeline ?? _loadLatestData),
                      icon: widget.isPipelineRunning
                          ? const SizedBox(
                              width: 14,
                              height: 14,
                              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                            )
                          : const Icon(Icons.play_arrow, size: 16, color: Colors.white),
                      label: Text(
                        widget.isPipelineRunning
                            ? (widget.pipelineStage.isNotEmpty ? widget.pipelineStage : 'ANALYZING...')
                            : 'RUN AUTONOMOUS ANALYSIS',
                        style: const TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.w700,
                          fontSize: 12,
                        ),
                      ),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF2563EB),
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                        elevation: 0,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
                      ),
                    ),
                  ],
                ),
              ],
            ),

            const SizedBox(height: 24),

            // Top KPI Cards
            LayoutBuilder(
              builder: (context, constraints) {
                final isNarrow = constraints.maxWidth < 700;
                final cards = [
                  _kpiCard(
                    title: 'INGESTED OBSERVATIONS',
                    value: totalRows > 0 ? '$totalRows' : '0',
                    subtext: _profile != null
                        ? '${_profile!.columnCount} Channels • ${_profile!.nominalInterval}'
                        : 'No telemetry loaded',
                    icon: Icons.dataset_outlined,
                    accentColor: const Color(0xFF2563EB),
                    onTap: widget.onNavigateToData,
                  ),
                  _kpiCard(
                    title: 'DATA HEALTH SCORE',
                    value: totalRows > 0 ? '${healthScore.toStringAsFixed(1)} / 100' : 'N/A',
                    subtext: _profile != null
                        ? '${_profile!.irregularGapsCount} Outage Gaps • ${_profile!.samplingRegularityPct.toStringAsFixed(0)}% Reg'
                        : 'Profile required',
                    icon: Icons.health_and_safety_outlined,
                    accentColor: const Color(0xFF059669),
                    onTap: widget.onNavigateToData,
                  ),
                  _kpiCard(
                    title: 'CONTEXTUAL BASELINE',
                    value: modelR2 > 0 ? 'R² = ${modelR2.toStringAsFixed(3)}' : 'Not Fitted',
                    subtext: modelR2 > 0 ? 'Multivariate Ridge Energy Baseline' : 'Run analysis to compute',
                    icon: Icons.show_chart,
                    accentColor: const Color(0xFFD97706),
                    onTap: widget.onNavigateToBaseline,
                  ),
                  _kpiCard(
                    title: 'ACTIVE ANOMALIES',
                    value: '${_anomalies.length}',
                    subtext: _anomalies.isNotEmpty
                        ? '${_anomalies.where((a) => a.severity == 'CRITICAL').length} Crit • ${_anomalies.where((a) => a.severity == 'HIGH').length} High • ${_anomalies.where((a) => a.severity == 'MEDIUM').length} Med'
                        : 'Persistent (≥3 intervals, verified)',
                    icon: Icons.warning_amber_rounded,
                    accentColor: const Color(0xFFDC2626),
                    onTap: widget.onInvestigate,
                  ),
                ];

                if (isNarrow) {
                  return Column(
                    children: cards.map((c) => Padding(padding: const EdgeInsets.only(bottom: 12), child: c)).toList(),
                  );
                }

                return Row(
                  children: cards.map((c) => Expanded(child: Padding(padding: const EdgeInsets.symmetric(horizontal: 6), child: c))).toList(),
                );
              },
            ),

            if (_anomalies.isNotEmpty) ...[
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
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
                child: Row(
                  children: [
                    const Icon(Icons.bolt, size: 16, color: Color(0xFFDC2626)),
                    const SizedBox(width: 8),
                    const Text(
                      'SEVERITY DISTRIBUTION:',
                      style: TextStyle(
                        color: Color(0xFF0F172A),
                        fontSize: 10.5,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 0.8,
                      ),
                    ),
                    const SizedBox(width: 14),
                    _anomalySeverityPill('CRITICAL', '${_anomalies.where((a) => a.severity == 'CRITICAL').length}', const Color(0xFFDC2626), widget.onInvestigate),
                    const SizedBox(width: 8),
                    _anomalySeverityPill('HIGH', '${_anomalies.where((a) => a.severity == 'HIGH').length}', const Color(0xFFEA580C), widget.onInvestigate),
                    const SizedBox(width: 8),
                    _anomalySeverityPill('MEDIUM', '${_anomalies.where((a) => a.severity == 'MEDIUM').length}', const Color(0xFFD97706), widget.onInvestigate),
                    const Spacer(),
                    TextButton.icon(
                      onPressed: widget.onInvestigate,
                      icon: const Icon(Icons.arrow_forward, size: 13, color: Color(0xFF2563EB)),
                      label: const Text('OPEN FULL TRIAGE MATRIX', style: TextStyle(color: Color(0xFF2563EB), fontSize: 11, fontWeight: FontWeight.bold)),
                    ),
                  ],
                ),
              ),
            ],

            const SizedBox(height: 24),

            // Monitored Chillers Grid (Dynamic entities)
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'MONITORED FACILITY CHILLERS',
                  style: TextStyle(
                    color: Color(0xFF64748B),
                    fontSize: 11,
                    letterSpacing: 1.2,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                if (entities.isNotEmpty)
                  Text(
                    '${entities.length} monitored equipment units',
                    style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 11),
                  ),
              ],
            ),
            const SizedBox(height: 12),

            if (entities.isEmpty)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: const Color(0xFFE2E8F0)),
                ),
                child: Center(
                  child: Column(
                    children: [
                      const Icon(Icons.hub_outlined, size: 32, color: Color(0xFF94A3B8)),
                      const SizedBox(height: 8),
                      const Text(
                        'No equipment entities discovered yet',
                        style: TextStyle(color: Color(0xFF0F172A), fontWeight: FontWeight.bold, fontSize: 13),
                      ),
                      const SizedBox(height: 4),
                      const Text(
                        'Click "RUN AUTONOMOUS ANALYSIS" to ingest and profile the dataset.',
                        style: TextStyle(color: Color(0xFF64748B), fontSize: 11),
                      ),
                    ],
                  ),
                ),
              )
            else
              LayoutBuilder(
                builder: (context, constraints) {
                  final isNarrow = constraints.maxWidth < 700;
                  final cards = entities.map((entityId) {
                    final readings = _profile?.countsPerEntity[entityId] ?? (totalRows ~/ entities.length);
                    final entAnoms = anomaliesByEntity[entityId] ?? [];
                    final anomCount = entAnoms.length;

                    // Status derivation
                    String status = 'NOMINAL';
                    Color statusColor = const Color(0xFF059669);
                    final hasCritical = entAnoms.any((a) => a.severity == 'CRITICAL');
                    if (hasCritical) {
                      status = 'CRITICAL';
                      statusColor = const Color(0xFFDC2626);
                    } else if (anomCount > 0) {
                      status = 'ANOMALY';
                      statusColor = const Color(0xFFD97706);
                    }

                    // Entity R2
                    final entModel = entityModels[entityId] as Map<String, dynamic>? ?? {};
                    final r2 = (entModel['r2'] as num?)?.toDouble() ?? modelR2;
                    final peakRes = entAnoms.isNotEmpty
                        ? '${entAnoms.first.residualScore >= 0 ? '+' : ''}${entAnoms.first.residualScore.toStringAsFixed(1)} kWh'
                        : '0.0 kWh';

                    return _chillerCard(
                      chillerId: entityId,
                      readings: readings,
                      status: status,
                      statusColor: statusColor,
                      r2: r2,
                      peakRes: peakRes,
                      anomaliesCount: anomCount,
                      onTap: () => widget.onSelectEquipment?.call(entityId),
                    );
                  }).toList();

                  if (isNarrow) {
                    return Column(
                      children: cards.map((c) => Padding(padding: const EdgeInsets.only(bottom: 12), child: c)).toList(),
                    );
                  }

                  return Row(
                    children: cards.map((c) => Expanded(child: Padding(padding: const EdgeInsets.symmetric(horizontal: 6), child: c))).toList(),
                  );
                },
              ),

            const SizedBox(height: 28),

            // Critical Anomaly Spotlight
            Container(
              padding: const EdgeInsets.all(20),
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
              child: topAnomaly == null
                  ? Row(
                      children: const [
                        Icon(Icons.check_circle_outline, color: Color(0xFF059669), size: 24),
                        SizedBox(width: 14),
                        Expanded(
                          child: Text(
                            'No critical anomalies recorded for active analysis. Run the autonomous pipeline to detect persistent deviations.',
                            style: TextStyle(color: Color(0xFF475569), fontSize: 12),
                          ),
                        ),
                      ],
                    )
                  : Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Wrap(
                          alignment: WrapAlignment.spaceBetween,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          spacing: 12,
                          runSpacing: 10,
                          children: [
                            Wrap(
                              crossAxisAlignment: WrapCrossAlignment.center,
                              spacing: 12,
                              runSpacing: 6,
                              children: [
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                  decoration: BoxDecoration(
                                    color: const Color(0xFFDC2626),
                                    borderRadius: BorderRadius.circular(3),
                                  ),
                                  child: const Text(
                                    'CRITICAL EPISODE',
                                    style: TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold),
                                  ),
                                ),
                                Text(
                                  '${topAnomaly.equipmentId} • ${topAnomaly.startTime} → ${topAnomaly.endTime}',
                                  style: const TextStyle(
                                    color: Color(0xFF0F172A),
                                    fontSize: 13,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ],
                            ),
                            OutlinedButton.icon(
                              onPressed: () {
                                widget.onSelectAnomaly?.call(topAnomaly.anomalyId);
                                widget.onInvestigate();
                              },
                              icon: const Icon(Icons.biotech, size: 14, color: Color(0xFF2563EB)),
                              label: const Text('INVESTIGATE EVIDENCE', style: TextStyle(color: Color(0xFF2563EB), fontSize: 11)),
                              style: OutlinedButton.styleFrom(
                                side: const BorderSide(color: Color(0xFF93C5FD)),
                                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        Text(
                          topAnomaly.interpretation.isNotEmpty
                              ? topAnomaly.interpretation
                              : 'Equipment exhibited sustained energy consumption deviation exceeding learned multivariate baseline under identical thermal lift conditions.',
                          style: const TextStyle(color: Color(0xFF475569), fontSize: 12, height: 1.4),
                        ),
                        const SizedBox(height: 14),
                        Wrap(
                          spacing: 12,
                          runSpacing: 8,
                          children: [
                            _spotlightMetric('Peak Z-Score', '${topAnomaly.peakZScore >= 0 ? '+' : ''}${topAnomaly.peakZScore.toStringAsFixed(1)} \u03c3', const Color(0xFFDC2626)),
                            _spotlightMetric('Persistence', '${topAnomaly.persistenceCount} Intervals (${topAnomaly.persistenceCount * 30} min)', const Color(0xFFD97706)),
                            _spotlightMetric('Peak Residual', '${topAnomaly.residualScore >= 0 ? '+' : ''}${topAnomaly.residualScore.toStringAsFixed(1)} kWh', const Color(0xFF2563EB)),
                            _spotlightMetric('Evidence Status', topAnomaly.status, const Color(0xFF059669)),
                          ],
                        ),
                      ],
                    ),
            ),

            const SizedBox(height: 24),

            // ── Multi-Layer Anomaly Audit Dashboard ──
            AnomalyDashboard(
              ipc: widget.ipc,
              selectedDataset: widget.selectedDataset,
              onInvestigate: widget.onInvestigate,
            ),

            const SizedBox(height: 16),
          ],
        ),
      ),
    );
  }

  Widget _kpiCard({
    required String title,
    required String value,
    required String subtext,
    required IconData icon,
    required Color accentColor,
    VoidCallback? onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(6),
      child: Container(
        padding: const EdgeInsets.all(16),
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
                Expanded(
                  child: Text(
                    title,
                    style: const TextStyle(color: Color(0xFF64748B), fontSize: 10, fontWeight: FontWeight.bold, letterSpacing: 0.4),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const SizedBox(width: 4),
                Icon(icon, size: 18, color: accentColor),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              value,
              style: const TextStyle(color: Color(0xFF0F172A), fontSize: 22, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 4),
            Text(
              subtext,
              style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 11.5),
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ),
      ),
    );
  }

  Widget _chillerCard({
    required String chillerId,
    required int readings,
    required String status,
    required Color statusColor,
    required double r2,
    required String peakRes,
    required int anomaliesCount,
    VoidCallback? onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(6),
      child: Container(
        padding: const EdgeInsets.all(16),
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
                Text(
                  chillerId,
                  style: const TextStyle(color: Color(0xFF0F172A), fontSize: 13.5, fontWeight: FontWeight.bold),
                ),
                const SizedBox(width: 4),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2.5),
                  decoration: BoxDecoration(
                    color: statusColor.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(3),
                  ),
                  child: Text(
                    status,
                    style: TextStyle(color: statusColor, fontSize: 10, fontWeight: FontWeight.bold),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            _dataRow('Readings', '$readings points'),
            const SizedBox(height: 4),
            _dataRow('Baseline Model Fit', 'R\u00b2 = ${r2.toStringAsFixed(3)}'),
            const SizedBox(height: 4),
            _dataRow('Peak Residual', peakRes),
            const SizedBox(height: 4),
            _dataRow('Persistent Anomalies', '$anomaliesCount episodes'),
          ],
        ),
      ),
    );
  }

  Widget _dataRow(String label, String value) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Expanded(
          child: Text(label, style: const TextStyle(color: Color(0xFF64748B), fontSize: 11), overflow: TextOverflow.ellipsis),
        ),
        const SizedBox(width: 4),
        Text(value, style: const TextStyle(color: Color(0xFF0F172A), fontSize: 11, fontWeight: FontWeight.w600)),
      ],
    );
  }

  Widget _spotlightMetric(String label, String value, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: const Color(0xFFF1F5F9),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: const Color(0xFFE2E8F0)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('$label: ', style: const TextStyle(color: Color(0xFF64748B), fontSize: 11)),
          Text(value, style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.bold)),
        ],
      ),
    );
  }

  Widget _anomalySeverityPill(String label, String count, Color color, VoidCallback? onTap) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(4),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(4),
          border: Border.all(color: color.withValues(alpha: 0.3)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 6,
              height: 6,
              decoration: BoxDecoration(color: color, shape: BoxShape.circle),
            ),
            const SizedBox(width: 6),
            Text(
              '$label: ',
              style: TextStyle(color: color, fontSize: 10.5, fontWeight: FontWeight.bold),
            ),
            Text(
              count,
              style: TextStyle(color: color, fontSize: 10.5, fontWeight: FontWeight.w800),
            ),
          ],
        ),
      ),
    );
  }
}
