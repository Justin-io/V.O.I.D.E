// Data models for V.O.I.D.E. UI State & IPC Protocol

enum UIState {
  workspaceSelected,
  fileOpen,
  terminalActive,
  browserActive,
  agentIdle,
  agentExecuting,
  agentAwaitingApproval,
  agentBlocked,
  agentVerifying,
  taskCompleted,
  errorRecovery,
}

class TaskRecord {
  final String taskId;
  final String objective;
  final String status;
  final String phase;
  final int currentStep;
  final int iteration;
  final int maxIterations;
  final String? lastAction;
  final String? lastObservation;
  final String? pendingApproval;

  TaskRecord({
    required this.taskId,
    required this.objective,
    required this.status,
    required this.phase,
    this.currentStep = 0,
    this.iteration = 0,
    this.maxIterations = 25,
    this.lastAction,
    this.lastObservation,
    this.pendingApproval,
  });

  factory TaskRecord.fromJson(Map<String, dynamic> json) {
    return TaskRecord(
      taskId: json['task_id'] as String? ?? '',
      objective: json['objective'] as String? ?? '',
      status: json['status'] as String? ?? 'AGENT_IDLE',
      phase: json['phase'] as String? ?? 'PLANNING',
      currentStep: json['current_step'] as int? ?? 0,
      iteration: json['iteration'] as int? ?? 0,
      maxIterations: json['max_iterations'] as int? ?? 25,
      lastAction: json['last_action'] as String?,
      lastObservation: json['last_observation'] as String?,
      pendingApproval: json['pending_approval'] as String?,
    );
  }
}

class AuditEvent {
  final String eventId;
  final String eventType;
  final String source;
  final String? taskId;
  final String priority;
  final Map<String, dynamic> data;
  final double timestamp;

  AuditEvent({
    required this.eventId,
    required this.eventType,
    required this.source,
    this.taskId,
    this.priority = 'NORMAL',
    required this.data,
    required this.timestamp,
  });

  factory AuditEvent.fromJson(Map<String, dynamic> json) {
    return AuditEvent(
      eventId: json['event_id'] as String? ?? '',
      eventType: json['event_type'] as String? ?? 'EVENT',
      source: json['source'] as String? ?? 'system',
      taskId: json['task_id'] as String?,
      priority: json['priority'] as String? ?? 'NORMAL',
      data: json['data'] as Map<String, dynamic>? ?? {},
      timestamp: (json['timestamp'] as num?)?.toDouble() ?? 0.0,
    );
  }
}

class FileEntry {
  final String name;
  final bool isDir;
  final int sizeBytes;
  final String path;

  FileEntry({
    required this.name,
    required this.isDir,
    required this.sizeBytes,
    required this.path,
  });

  bool get isDirectory => isDir;

  factory FileEntry.fromJson(Map<String, dynamic> json) {
    return FileEntry(
      name: json['name'] as String? ?? '',
      isDir: json['is_dir'] as bool? ?? false,
      sizeBytes: json['size_bytes'] as int? ?? 0,
      path: json['path'] as String? ?? '',
    );
  }
}

class ChatSession {
  final String sessionId;
  final String workspaceRoot;
  final String title;
  final double createdAt;
  final double updatedAt;
  final int messageCount;

  ChatSession({
    required this.sessionId,
    required this.workspaceRoot,
    required this.title,
    required this.createdAt,
    required this.updatedAt,
    this.messageCount = 0,
  });

  factory ChatSession.fromJson(Map<String, dynamic> json) {
    return ChatSession(
      sessionId: json['session_id'] as String? ?? '',
      workspaceRoot: json['workspace_root'] as String? ?? '',
      title: json['title'] as String? ?? 'Untitled Chat',
      createdAt: (json['created_at'] as num?)?.toDouble() ?? 0.0,
      updatedAt: (json['updated_at'] as num?)?.toDouble() ?? 0.0,
      messageCount: (json['message_count'] as num?)?.toInt() ?? 0,
    );
  }
}

class EditorTab {
  final String path;
  final String name;
  String content;
  bool isDirty;

  EditorTab({
    required this.path,
    required this.name,
    required this.content,
    this.isDirty = false,
  });
}

// ----------------- Engineering Data Intelligence Models -----------------

class DatasetSummary {
  final String datasetId;
  final String name;
  final String filePath;
  final String fileHash;
  final int rowCount;
  final int columnCount;
  final String format;
  final List<String> columns;

  DatasetSummary({
    required this.datasetId,
    required this.name,
    required this.filePath,
    required this.fileHash,
    required this.rowCount,
    required this.columnCount,
    required this.format,
    required this.columns,
  });

  factory DatasetSummary.fromJson(Map<String, dynamic> json) {
    return DatasetSummary(
      datasetId: json['dataset_id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      filePath: json['file_path'] as String? ?? '',
      fileHash: json['file_hash'] as String? ?? '',
      rowCount: (json['row_count'] as num?)?.toInt() ?? 0,
      columnCount: (json['column_count'] as num?)?.toInt() ?? 0,
      format: json['format'] as String? ?? 'csv',
      columns: (json['columns'] as List<dynamic>?)?.map((e) => e.toString()).toList() ?? [],
    );
  }
}

class DataProfile {
  final int rowCount;
  final int columnCount;
  final String primaryTimeColumn;
  final String primaryEntityColumn;
  final double dataHealthScore;
  final String nominalInterval;
  final int irregularGapsCount;
  final double samplingRegularityPct;
  final String primaryTargetColumn;
  final String primaryLoadColumn;
  final List<String> featureColumns;
  final List<String> entities;
  final Map<String, int> countsPerEntity;
  final Map<String, dynamic> missingness;
  final Map<String, dynamic> columnSummaries;

  DataProfile({
    required this.rowCount,
    required this.columnCount,
    required this.primaryTimeColumn,
    required this.primaryEntityColumn,
    required this.dataHealthScore,
    required this.nominalInterval,
    required this.irregularGapsCount,
    this.samplingRegularityPct = 100.0,
    this.primaryTargetColumn = '',
    this.primaryLoadColumn = '',
    this.featureColumns = const [],
    required this.entities,
    required this.countsPerEntity,
    required this.missingness,
    this.columnSummaries = const {},
  });

  factory DataProfile.fromJson(Map<String, dynamic> json) {
    final entitySumm = json['entity_summary'] as Map<String, dynamic>? ?? {};
    final tempProf = json['temporal_profile'] as Map<String, dynamic>? ?? {};
    final counts = entitySumm['counts_per_entity'] as Map<String, dynamic>? ?? {};
    final featList = (json['feature_columns'] as List<dynamic>?)?.map((e) => e.toString()).toList() ?? [];
    final colSumms = json['column_summaries'] as Map<String, dynamic>? ?? {};

    return DataProfile(
      rowCount: (json['row_count'] as num?)?.toInt() ?? 0,
      columnCount: (json['column_count'] as num?)?.toInt() ?? 0,
      primaryTimeColumn: json['primary_time_column'] as String? ?? 'timestamp',
      primaryEntityColumn: json['primary_entity_column'] as String? ?? 'equipment_id',
      dataHealthScore: (json['data_health_score'] as num?)?.toDouble() ?? 100.0,
      nominalInterval: tempProf['nominal_interval_human'] as String? ?? '30 minutes',
      irregularGapsCount: (tempProf['irregular_gaps_count'] as num?)?.toInt() ?? 0,
      samplingRegularityPct: (tempProf['sampling_regularity_pct'] as num?)?.toDouble() ?? 100.0,
      primaryTargetColumn: json['primary_target_column'] as String? ?? '',
      primaryLoadColumn: json['primary_load_column'] as String? ?? '',
      featureColumns: featList,
      entities: (entitySumm['entities'] as List<dynamic>?)?.map((e) => e.toString()).toList() ?? [],
      countsPerEntity: counts.map((k, v) => MapEntry(k, (v as num).toInt())),
      missingness: json['missingness'] as Map<String, dynamic>? ?? {},
      columnSummaries: colSumms,
    );
  }
}

class AnalysisRecord {
  final String analysisId;
  final String datasetName;
  final String timestamp;
  final double modelR2;
  final int anomaliesCount;
  final Map<String, dynamic> raw;

  AnalysisRecord({
    required this.analysisId,
    required this.datasetName,
    required this.timestamp,
    required this.modelR2,
    required this.anomaliesCount,
    required this.raw,
  });

  factory AnalysisRecord.fromJson(Map<String, dynamic> json) {
    return AnalysisRecord(
      analysisId: json['analysis_id'] as String? ?? '',
      datasetName: json['dataset_name'] as String? ?? '',
      timestamp: json['timestamp'] as String? ?? '',
      modelR2: (json['model_r2'] as num?)?.toDouble() ?? 0.0,
      anomaliesCount: (json['anomalies_detected'] as num?)?.toInt() ?? 0,
      raw: json,
    );
  }
}

class AnomalyRecord {
  final String anomalyId;
  final String evidenceId;
  final String equipmentId;
  final String startTime;
  final String endTime;
  final String severity;
  final int persistenceCount;
  final double residualScore;
  final double peakZScore;
  final double multivariateScore;
  final double confidence;
  final String status;
  final String interpretation;
  final Map<String, dynamic> evidence;

  AnomalyRecord({
    required this.anomalyId,
    required this.evidenceId,
    required this.equipmentId,
    required this.startTime,
    required this.endTime,
    required this.severity,
    required this.persistenceCount,
    required this.residualScore,
    required this.peakZScore,
    required this.multivariateScore,
    required this.confidence,
    required this.status,
    required this.interpretation,
    required this.evidence,
  });

  factory AnomalyRecord.fromJson(Map<String, dynamic> json) {
    return AnomalyRecord(
      anomalyId: json['anomaly_id'] as String? ?? '',
      evidenceId: json['evidence_id'] as String? ?? '',
      equipmentId: json['equipment_id'] as String? ?? '',
      startTime: json['start_time'] as String? ?? '',
      endTime: json['end_time'] as String? ?? '',
      severity: json['severity'] as String? ?? 'MEDIUM',
      persistenceCount: (json['persistence_count'] as num?)?.toInt() ?? 1,
      residualScore: (json['residual_score'] as num?)?.toDouble() ?? 0.0,
      peakZScore: (json['peak_z_score'] as num?)?.toDouble() ?? 0.0,
      multivariateScore: (json['multivariate_score'] as num?)?.toDouble() ?? 0.0,
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0.8,
      status: json['status'] as String? ?? 'CONFIRMED',
      interpretation: json['interpretation'] as String? ?? '',
      evidence: json['evidence'] as Map<String, dynamic>? ?? {},
    );
  }
}

class VisualArtifact {
  final String artifactId;
  final String visualType;
  final String title;
  final String filePath;

  VisualArtifact({
    required this.artifactId,
    required this.visualType,
    required this.title,
    required this.filePath,
  });

  factory VisualArtifact.fromJson(Map<String, dynamic> json) {
    return VisualArtifact(
      artifactId: json['artifact_id'] as String? ?? '',
      visualType: json['visual_type'] as String? ?? '',
      title: json['title'] as String? ?? '',
      filePath: json['file_path'] as String? ?? '',
    );
  }
}

class ReportRecord {
  final String reportId;
  final String analysisId;
  final String title;
  final String contentMarkdown;
  final String filePath;

  ReportRecord({
    required this.reportId,
    required this.analysisId,
    required this.title,
    required this.contentMarkdown,
    required this.filePath,
  });

  factory ReportRecord.fromJson(Map<String, dynamic> json) {
    return ReportRecord(
      reportId: json['report_id'] as String? ?? '',
      analysisId: json['analysis_id'] as String? ?? '',
      title: json['title'] as String? ?? '',
      contentMarkdown: json['content_markdown'] as String? ?? '',
      filePath: json['file_path'] as String? ?? '',
    );
  }
}

