import 'package:flutter/material.dart';
import '../models/ipc_models.dart';

enum RailTab {
  overview,
  data,
  analysis,
  investigation,
  visuals,
  report,
  browser,
  files,
  settings,
}

class WorkspaceRail extends StatefulWidget {
  final RailTab activeTab;
  final List<FileEntry> files;
  final ValueChanged<String> onFileSelected;
  final String activeFilePath;
  final String workspacePath;
  final ValueChanged<RailTab>? onTabChanged;
  final VoidCallback? onOpenFolder;
  final VoidCallback? onNewFile;
  final VoidCallback? onNewFolder;
  final VoidCallback? onRefreshFiles;
  final Function(String path)? onDeleteFile;
  final Function(String oldPath, String newPath)? onRenameFile;
  final int anomalyCount;

  const WorkspaceRail({
    super.key,
    required this.activeTab,
    required this.files,
    required this.onFileSelected,
    required this.activeFilePath,
    this.workspacePath = '',
    this.onTabChanged,
    this.onOpenFolder,
    this.onNewFile,
    this.onNewFolder,
    this.onRefreshFiles,
    this.onDeleteFile,
    this.onRenameFile,
    this.anomalyCount = 0,
  });

  @override
  State<WorkspaceRail> createState() => _WorkspaceRailState();
}

class _WorkspaceRailState extends State<WorkspaceRail> {
  @override
  Widget build(BuildContext context) {
    final showFileDrawer = widget.activeTab == RailTab.files;

    return Row(
      children: [
        // Primary Engineering Navigation Rail
        Container(
          width: 72,
          decoration: const BoxDecoration(
            color: Color(0xFFFFFFFF),
            border: Border(right: BorderSide(color: Color(0xFFE2E8F0))),
          ),
          child: Column(
            children: [
              const SizedBox(height: 12),
              _railItem(
                tab: RailTab.overview,
                icon: Icons.dashboard_outlined,
                activeIcon: Icons.dashboard,
                label: 'OVERVIEW',
                tooltip: 'Facility Mission Control & Fleet KPIs',
              ),
              _railItem(
                tab: RailTab.data,
                icon: Icons.storage_outlined,
                activeIcon: Icons.storage,
                label: 'DATASET',
                tooltip: 'Data Ingestion & Profiling',
              ),
              _railItem(
                tab: RailTab.analysis,
                icon: Icons.analytics_outlined,
                activeIcon: Icons.analytics,
                label: 'BASELINE',
                tooltip: 'Contextual Analysis & Baseline',
              ),
              _railItem(
                tab: RailTab.investigation,
                icon: Icons.biotech_outlined,
                activeIcon: Icons.biotech,
                label: 'TRIAGE',
                tooltip: 'Investigation & Evidence Chain',
                badgeText: widget.anomalyCount > 0 ? '${widget.anomalyCount}' : null,
                badgeColor: const Color(0xFFEF4444),
              ),
              _railItem(
                tab: RailTab.visuals,
                icon: Icons.image_outlined,
                activeIcon: Icons.image,
                label: 'VISUALS',
                tooltip: 'Visual Intelligence & Schematics',
              ),
              _railItem(
                tab: RailTab.report,
                icon: Icons.description_outlined,
                activeIcon: Icons.description,
                label: 'REPORT',
                tooltip: 'Engineering Reports',
              ),
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                child: Divider(height: 1, color: Color(0xFFE2E8F0)),
              ),
              _railItem(
                tab: RailTab.browser,
                icon: Icons.hub_outlined,
                activeIcon: Icons.hub,
                label: 'GATEWAY',
                tooltip: 'LLM Model Gateway & Web Viewport',
              ),
              _railItem(
                tab: RailTab.files,
                icon: Icons.folder_outlined,
                activeIcon: Icons.folder,
                label: 'FILES',
                tooltip: 'Workspace Files',
              ),
              const Spacer(),
              _railItem(
                tab: RailTab.settings,
                icon: Icons.settings_outlined,
                activeIcon: Icons.settings,
                label: 'SYSTEM',
                tooltip: 'Settings & Runtime',
              ),
              const SizedBox(height: 12),
            ],
          ),
        ),

        // Collapsible Workspace File Explorer Drawer
        if (showFileDrawer)
          Container(
            width: 220,
            decoration: const BoxDecoration(
              color: Color(0xFFF8FAFC),
              border: Border(right: BorderSide(color: Color(0xFFE2E8F0))),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Drawer Header
                Container(
                  height: 40,
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  decoration: const BoxDecoration(
                    border: Border(bottom: BorderSide(color: Color(0xFFE2E8F0))),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text(
                        'EXPLORER',
                        style: TextStyle(
                          color: Color(0xFF0F172A),
                          fontSize: 10,
                          fontWeight: FontWeight.bold,
                          letterSpacing: 1.0,
                        ),
                      ),
                      Row(
                        children: [
                          _iconBtn(Icons.create_new_folder_outlined, 'New Folder', widget.onNewFolder),
                          _iconBtn(Icons.note_add_outlined, 'New File', widget.onNewFile),
                          _iconBtn(Icons.refresh, 'Refresh', widget.onRefreshFiles),
                        ],
                      ),
                    ],
                  ),
                ),
                // Workspace Root Label
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  child: Row(
                    children: [
                      const Icon(Icons.folder_open, size: 14, color: Color(0xFF2563EB)),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          widget.workspacePath.isNotEmpty
                              ? widget.workspacePath.split('/').last
                              : 'NO FOLDER',
                          style: const TextStyle(
                            color: Color(0xFF334155),
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                          ),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ),
                const Divider(height: 1, color: Color(0xFFE2E8F0)),
                // File List
                Expanded(
                  child: widget.files.isEmpty
                      ? Center(
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              const Icon(Icons.folder_open, size: 28, color: Color(0xFF94A3B8)),
                              const SizedBox(height: 8),
                              const Text('No files loaded', style: TextStyle(color: Color(0xFF64748B), fontSize: 11)),
                              const SizedBox(height: 8),
                              OutlinedButton(
                                onPressed: widget.onOpenFolder,
                                style: OutlinedButton.styleFrom(
                                  side: const BorderSide(color: Color(0xFFCBD5E1)),
                                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                                ),
                                child: const Text('Open Folder', style: TextStyle(color: Color(0xFF2563EB), fontSize: 10)),
                              ),
                            ],
                          ),
                        )
                      : ListView.builder(
                          itemCount: widget.files.length,
                          itemBuilder: (context, index) {
                            final f = widget.files[index];
                            final isSel = widget.activeFilePath == f.path;
                            return InkWell(
                              onTap: () => widget.onFileSelected(f.path),
                              child: Container(
                                height: 26,
                                padding: const EdgeInsets.symmetric(horizontal: 12),
                                color: isSel ? const Color(0xFFEFF6FF) : Colors.transparent,
                                child: Row(
                                  children: [
                                    Icon(
                                      f.isDir ? Icons.folder : _fileIcon(f.name),
                                      size: 13,
                                      color: f.isDir
                                          ? const Color(0xFF2563EB)
                                          : (isSel ? const Color(0xFF2563EB) : const Color(0xFF64748B)),
                                    ),
                                    const SizedBox(width: 8),
                                    Expanded(
                                      child: Text(
                                        f.name,
                                        style: TextStyle(
                                          color: isSel ? const Color(0xFF2563EB) : const Color(0xFF334155),
                                          fontSize: 11,
                                          fontWeight: isSel ? FontWeight.bold : FontWeight.normal,
                                        ),
                                        overflow: TextOverflow.ellipsis,
                                      ),
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
      ],
    );
  }

  Widget _railItem({
    required RailTab tab,
    required IconData icon,
    required IconData activeIcon,
    required String label,
    required String tooltip,
    String? badgeText,
    Color? badgeColor,
  }) {
    final isSelected = widget.activeTab == tab;

    return Tooltip(
      message: tooltip,
      preferBelow: false,
      waitDuration: const Duration(milliseconds: 300),
      child: InkWell(
        onTap: () => widget.onTabChanged?.call(tab),
        child: Container(
          width: 64,
          padding: const EdgeInsets.symmetric(vertical: 8),
          decoration: BoxDecoration(
            border: Border(
              left: BorderSide(
                color: isSelected ? const Color(0xFF2563EB) : Colors.transparent,
                width: 3,
              ),
            ),
            color: isSelected ? const Color(0xFFEFF6FF) : Colors.transparent,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Stack(
                clipBehavior: Clip.none,
                children: [
                  Icon(
                    isSelected ? activeIcon : icon,
                    size: 22,
                    color: isSelected ? const Color(0xFF2563EB) : const Color(0xFF64748B),
                  ),
                  if (badgeText != null)
                    Positioned(
                      top: -5,
                      right: -10,
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
                        decoration: BoxDecoration(
                           color: badgeColor ?? const Color(0xFFEF4444),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          badgeText,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 8.5,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 5),
              Text(
                label,
                style: TextStyle(
                  color: isSelected ? const Color(0xFF2563EB) : const Color(0xFF64748B),
                  fontSize: 10,
                  fontWeight: isSelected ? FontWeight.w800 : FontWeight.w600,
                  letterSpacing: 0.5,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _iconBtn(IconData icon, String tip, VoidCallback? action) {
    return Tooltip(
      message: tip,
      child: InkWell(
        onTap: action,
        borderRadius: BorderRadius.circular(3),
        child: Padding(
          padding: const EdgeInsets.all(4),
          child: Icon(icon, size: 14, color: const Color(0xFF64748B)),
        ),
      ),
    );
  }

  IconData _fileIcon(String name) {
    if (name.endsWith('.csv')) return Icons.table_chart_outlined;
    if (name.endsWith('.py')) return Icons.code;
    if (name.endsWith('.dart')) return Icons.flutter_dash;
    if (name.endsWith('.json')) return Icons.data_object;
    if (name.endsWith('.md')) return Icons.description_outlined;
    if (name.endsWith('.png') || name.endsWith('.jpg')) return Icons.image_outlined;
    return Icons.insert_drive_file_outlined;
  }
}
