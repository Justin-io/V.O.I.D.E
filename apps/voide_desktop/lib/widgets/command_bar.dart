import 'package:flutter/material.dart';

class GlobalCommandBar extends StatelessWidget {
  final bool isConnected;
  final String workspacePath;
  final VoidCallback onRefresh;
  final int? port;
  final String selectedDataset;
  final List<String> availableDatasets;
  final VoidCallback? onSelectDataset;
  final String selectedEquipment;
  final List<String> availableEquipment;
  final ValueChanged<String>? onEquipmentSelected;
  final bool isPipelineRunning;
  final String pipelineStage;
  final double pipelineProgress;
  final VoidCallback? onRunPipeline;
  final bool isAgentPanelOpen;
  final VoidCallback? onToggleAgentPanel;

  const GlobalCommandBar({
    super.key,
    required this.isConnected,
    required this.workspacePath,
    required this.onRefresh,
    this.port,
    this.selectedDataset = 'development_dataset.csv',
    this.availableDatasets = const ['development_dataset.csv'],
    this.onSelectDataset,
    this.selectedEquipment = '',
    this.availableEquipment = const [],
    this.onEquipmentSelected,
    this.isPipelineRunning = false,
    this.pipelineStage = '',
    this.pipelineProgress = 0.0,
    this.onRunPipeline,
    this.isAgentPanelOpen = true,
    this.onToggleAgentPanel,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 52,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: const BoxDecoration(
        color: Color(0xFFFFFFFF),
        border: Border(
          bottom: BorderSide(color: Color(0xFFE2E8F0), width: 1),
        ),
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          return SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: ConstrainedBox(
              constraints: BoxConstraints(minWidth: constraints.maxWidth),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  // Left: Brand, Dataset, Equipment Filter
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      // Brand & Title
                      Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
                            decoration: BoxDecoration(
                              gradient: const LinearGradient(
                                colors: [Color(0xFF2563EB), Color(0xFF1D4ED8)],
                              ),
                              borderRadius: BorderRadius.circular(4),
                              boxShadow: [
                                BoxShadow(
                                  color: const Color(0xFF2563EB).withValues(alpha: 0.2),
                                  blurRadius: 4,
                                  offset: const Offset(0, 1),
                                ),
                              ],
                            ),
                            child: const Text(
                              'V.O.I.D.E.',
                              style: TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.w900,
                                fontSize: 12,
                                letterSpacing: 1.5,
                              ),
                            ),
                          ),
                          const SizedBox(width: 10),
                          const Text(
                            'DATA INTELLIGENCE WORKSTATION',
                            style: TextStyle(
                              color: Color(0xFF64748B),
                              fontSize: 10.5,
                              fontWeight: FontWeight.w700,
                              letterSpacing: 1.2,
                            ),
                          ),
                        ],
                      ),

                      const SizedBox(width: 18),

                      // Dynamic Dataset Pill (Clickable to switch / upload)
                      InkWell(
                        onTap: onSelectDataset,
                        borderRadius: BorderRadius.circular(4),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(
                            color: const Color(0xFFF8FAFC),
                            borderRadius: BorderRadius.circular(4),
                            border: Border.all(color: const Color(0xFFCBD5E1)),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(Icons.dataset_outlined, size: 13, color: Color(0xFF2563EB)),
                              const SizedBox(width: 6),
                              const Text(
                                'WORKSPACE',
                                style: TextStyle(
                                  color: Color(0xFF2563EB),
                                  fontSize: 9,
                                  fontWeight: FontWeight.w800,
                                  letterSpacing: 0.8,
                                ),
                              ),
                              const SizedBox(width: 6),
                              Text(
                                selectedDataset.isNotEmpty ? selectedDataset : 'No Dataset Selected',
                                style: const TextStyle(
                                  color: Color(0xFF0F172A),
                                  fontSize: 11,
                                  fontWeight: FontWeight.w600,
                                  fontFamily: 'monospace',
                                ),
                              ),
                              const SizedBox(width: 4),
                              const Icon(Icons.arrow_drop_down, size: 14, color: Color(0xFF64748B)),
                            ],
                          ),
                        ),
                      ),

                      const SizedBox(width: 14),

                      // Dynamic Equipment Filter Selector
                      if (availableEquipment.isNotEmpty && onEquipmentSelected != null)
                        Container(
                          padding: const EdgeInsets.all(2),
                          decoration: BoxDecoration(
                            color: const Color(0xFFF1F5F9),
                            borderRadius: BorderRadius.circular(5),
                            border: Border.all(color: const Color(0xFFE2E8F0)),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: availableEquipment.map((eq) {
                              final shortName = eq.replaceAll('CHILLER-', 'CH-');
                              return _equipFilterPill(eq, shortName);
                            }).toList(),
                          ),
                        ),
                    ],
                  ),

                  const SizedBox(width: 16),

                  // Right: Pipeline Run / Progress, Agent Panel, Connection
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      // Autonomous Pipeline Trigger / Progress Pill
                      if (isPipelineRunning)
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
                          decoration: BoxDecoration(
                            color: const Color(0xFFEFF6FF),
                            borderRadius: BorderRadius.circular(4),
                            border: Border.all(color: const Color(0xFF93C5FD)),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const SizedBox(
                                width: 12,
                                height: 12,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  valueColor: AlwaysStoppedAnimation<Color>(Color(0xFF2563EB)),
                                ),
                              ),
                              const SizedBox(width: 8),
                              Text(
                                pipelineStage.isNotEmpty ? '$pipelineStage (${(pipelineProgress * 100).toInt()}%)' : 'RUNNING...',
                                style: const TextStyle(
                                  color: Color(0xFF2563EB),
                                  fontSize: 10,
                                  fontWeight: FontWeight.bold,
                                  letterSpacing: 0.8,
                                ),
                              ),
                            ],
                          ),
                        )
                      else if (onRunPipeline != null)
                        ElevatedButton.icon(
                          onPressed: onRunPipeline,
                          icon: const Icon(Icons.play_arrow, size: 14, color: Colors.white),
                          label: const Text(
                            'RUN ANALYSIS',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 10,
                              fontWeight: FontWeight.w800,
                              letterSpacing: 0.8,
                            ),
                          ),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: const Color(0xFF2563EB),
                            foregroundColor: Colors.white,
                            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
                            elevation: 0,
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
                          ),
                        ),

                      const SizedBox(width: 10),

                      // Agent Intelligence Panel Toggle
                      if (onToggleAgentPanel != null)
                        InkWell(
                          onTap: onToggleAgentPanel,
                          borderRadius: BorderRadius.circular(4),
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                            decoration: BoxDecoration(
                              color: isAgentPanelOpen ? const Color(0xFFEFF6FF) : const Color(0xFFFFFFFF),
                              borderRadius: BorderRadius.circular(4),
                              border: Border.all(
                                color: isAgentPanelOpen ? const Color(0xFF2563EB) : const Color(0xFFCBD5E1),
                              ),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  Icons.smart_toy_outlined,
                                  size: 13,
                                  color: isAgentPanelOpen ? const Color(0xFF2563EB) : const Color(0xFF64748B),
                                ),
                                const SizedBox(width: 6),
                                Text(
                                  'COPILOT',
                                  style: TextStyle(
                                    color: isAgentPanelOpen ? const Color(0xFF2563EB) : const Color(0xFF475569),
                                    fontSize: 9,
                                    fontWeight: FontWeight.w700,
                                    letterSpacing: 0.6,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),

                      const SizedBox(width: 10),

                      // IPC Status Indicator
                      Tooltip(
                        message: isConnected ? 'IPC Active on port ${port ?? 8766}' : 'Connecting to local runtime...',
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
                          decoration: BoxDecoration(
                            color: isConnected ? const Color(0xFFECFDF5) : const Color(0xFFFEF2F2),
                            borderRadius: BorderRadius.circular(4),
                            border: Border.all(
                              color: isConnected ? const Color(0xFFA7F3D0) : const Color(0xFFFECACA),
                            ),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Container(
                                width: 7,
                                height: 7,
                                decoration: BoxDecoration(
                                  color: isConnected ? const Color(0xFF10B981) : const Color(0xFFEF4444),
                                  shape: BoxShape.circle,
                                ),
                              ),
                              const SizedBox(width: 5),
                              Text(
                                isConnected ? 'LIVE' : 'OFFLINE',
                                style: TextStyle(
                                  color: isConnected ? const Color(0xFF047857) : const Color(0xFFB91C1C),
                                  fontSize: 9,
                                  fontWeight: FontWeight.w800,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _equipFilterPill(String fullId, String label) {
    final isSelected = selectedEquipment == fullId;
    return InkWell(
      onTap: () => onEquipmentSelected?.call(fullId),
      borderRadius: BorderRadius.circular(3),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 120),
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4.5),
        decoration: BoxDecoration(
          color: isSelected ? const Color(0xFFEFF6FF) : Colors.transparent,
          borderRadius: BorderRadius.circular(3),
          border: Border.all(
            color: isSelected ? const Color(0xFF2563EB) : Colors.transparent,
            width: 1,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: isSelected ? const Color(0xFF2563EB) : const Color(0xFF64748B),
            fontSize: 11,
            fontWeight: isSelected ? FontWeight.w800 : FontWeight.w500,
          ),
        ),
      ),
    );
  }
}
