import 'package:flutter/material.dart';

enum OrderStatus {
  issued('Выдан', Color(0xFF607D8B)),
  accepted('Принят', Color(0xFF1E88E5)),
  queued('В очереди', Color(0xFF3949AB)),
  inProgress('В работе', Color(0xFFF9A825)),
  paused('Приостановлен', Color(0xFFFF7043)),
  completed('Исполнен', Color(0xFF43A047)),
  closed('Принят мастером', Color(0xFF2E7D32)),
  rejected('Отклонён', Color(0xFFD32F2F)),
  cancelled('Отменён', Color(0xFF9E9E9E));

  const OrderStatus(this.label, this.color);
  final String label;
  final Color color;

  static OrderStatus parse(String v) =>
      v == 'in_progress' ? inProgress : OrderStatus.values.byName(v);

  bool get isActive =>
      const {issued, accepted, queued, inProgress, paused}.contains(this);
}

enum OrderType {
  planned('Плановый'),
  emergency('Аварийный');

  const OrderType(this.label);
  final String label;
}

enum Priority {
  low('Низкий'),
  medium('Средний'),
  high('Высокий'),
  critical('Критический');

  const Priority(this.label);
  final String label;
}

/// Действия над нарядом — совпадают с `allowed_actions` бэкенда.
enum OrderAction {
  accept('Принять в работу', Icons.check_circle_outline, needsReason: false),
  queue('Поставить в очередь', Icons.playlist_add, needsReason: false),
  reject('Отклонить', Icons.block, needsReason: true),
  start('Начать исполнение', Icons.play_arrow, needsReason: false),
  pause('Приостановить', Icons.pause, needsReason: true),
  complete('Исполнено', Icons.task_alt, needsReason: false),
  approve('Принять работу', Icons.verified, needsReason: false),
  returnBack('Вернуть на доработку', Icons.undo, needsReason: true),
  reassign('Переназначить', Icons.swap_horiz, needsReason: false),
  cancel('Отменить наряд', Icons.cancel_outlined, needsReason: true);

  const OrderAction(this.label, this.icon, {required this.needsReason});
  final String label;
  final IconData icon;
  final bool needsReason;

  String get apiName => this == returnBack ? 'return' : name;

  static OrderAction? tryParse(String v) {
    if (v == 'return') return returnBack;
    for (final a in values) {
      if (a.name == v) return a;
    }
    return null;
  }
}

class Person {
  const Person({required this.id, required this.fio, this.specialty});
  final int id;
  final String fio;
  final String? specialty;

  factory Person.fromJson(Map<String, dynamic> j) =>
      Person(id: j['id'], fio: j['fio'], specialty: j['specialty']);
}

class WorkOrder {
  const WorkOrder({
    required this.id,
    required this.number,
    required this.type,
    required this.description,
    required this.workshopName,
    required this.equipmentName,
    required this.executor,
    required this.master,
    required this.priority,
    required this.deadline,
    required this.status,
    required this.isOverdue,
    required this.equipmentStopped,
    required this.createdAt,
    required this.allowedActions,
  });

  final int id;
  final String number;
  final OrderType type;
  final String description;
  final String workshopName;
  final String? equipmentName;
  final Person? executor;
  final Person master;
  final Priority priority;
  final DateTime deadline;
  final OrderStatus status;
  final bool isOverdue;
  final bool equipmentStopped;
  final DateTime createdAt;
  final List<OrderAction> allowedActions;

  bool get isEmergency => type == OrderType.emergency;

  factory WorkOrder.fromJson(Map<String, dynamic> j) => WorkOrder(
    id: j['id'],
    number: j['number'] ?? '#${j['id']}',
    type: OrderType.values.byName(j['type']),
    description: j['description'],
    workshopName: j['workshop']['name'],
    equipmentName: j['equipment']?['name'],
    executor: j['executor'] == null ? null : Person.fromJson(j['executor']),
    master: Person.fromJson(j['master']),
    priority: Priority.values.byName(j['priority']),
    deadline: DateTime.parse(j['deadline']).toLocal(),
    status: OrderStatus.parse(j['status']),
    isOverdue: j['is_overdue'] ?? false,
    equipmentStopped: j['equipment_stopped'] ?? false,
    createdAt: DateTime.parse(j['created_at']).toLocal(),
    allowedActions: [
      for (final a in (j['allowed_actions'] as List? ?? const []))
        ?OrderAction.tryParse(a as String),
    ],
  );
}

class OrderPhoto {
  const OrderPhoto({
    required this.id,
    required this.isAfter,
    required this.url,
  });
  final int id;
  final bool isAfter;
  final String url;

  factory OrderPhoto.fromJson(Map<String, dynamic> j) =>
      OrderPhoto(id: j['id'], isAfter: j['type'] == 'after', url: j['url']);
}

class OrderEvent {
  const OrderEvent({
    required this.action,
    required this.timestamp,
    this.toStatus,
    this.reason,
    this.userName,
  });
  final String action;
  final DateTime timestamp;
  final OrderStatus? toStatus;
  final String? reason;
  final String? userName;

  factory OrderEvent.fromJson(Map<String, dynamic> j) => OrderEvent(
    action: j['action'],
    timestamp: DateTime.parse(j['timestamp']).toLocal(),
    toStatus: j['to_status'] == null ? null : OrderStatus.parse(j['to_status']),
    reason: j['reason'],
    userName: j['user']?['fio'],
  );
}

class AiCheck {
  const AiCheck({
    required this.name,
    required this.severity,
    required this.message,
  });
  final String name;
  final String severity;
  final String message;
}

class AiReport {
  const AiReport({
    required this.verdict,
    required this.score,
    required this.photoScore,
    required this.explanation,
    required this.checks,
    required this.source,
  });

  final String verdict;
  final double score;
  final double? photoScore;
  final String explanation;
  final List<AiCheck> checks;
  final String source;

  String get verdictLabel => switch (verdict) {
    'ok' => 'Замечаний нет',
    'needs_review' => 'Нужна проверка',
    _ => 'Есть нарушения',
  };

  Color get color => switch (verdict) {
    'ok' => const Color(0xFF2E7D32),
    'needs_review' => const Color(0xFFF9A825),
    _ => const Color(0xFFD32F2F),
  };

  factory AiReport.fromJson(Map<String, dynamic> j) => AiReport(
    verdict: j['verdict'],
    score: (j['score'] as num).toDouble(),
    photoScore: (j['photo_score'] as num?)?.toDouble(),
    explanation: j['explanation'],
    source: j['source'],
    checks: [
      for (final c in (j['checks'] as List? ?? const []))
        AiCheck(
          name: c['name'],
          severity: c['severity'],
          message: c['message'],
        ),
    ],
  );
}

class UsedMaterial {
  const UsedMaterial({
    required this.name,
    required this.quantity,
    required this.unit,
  });
  final String name;
  final double quantity;
  final String unit;
}

class OrderDetail {
  const OrderDetail({
    required this.order,
    required this.workReport,
    required this.faultCode,
    required this.photos,
    required this.events,
    required this.materials,
    required this.aiReport,
  });

  final WorkOrder order;
  final String? workReport;
  final String? faultCode;
  final List<OrderPhoto> photos;
  final List<OrderEvent> events;
  final List<UsedMaterial> materials;
  final AiReport? aiReport;

  factory OrderDetail.fromJson(Map<String, dynamic> j) => OrderDetail(
    order: WorkOrder.fromJson(j),
    workReport: j['work_report'],
    faultCode: j['fault_code'] == null
        ? null
        : '${j['fault_code']['code']} ${j['fault_code']['name']}',
    photos: [for (final p in j['photos'] as List) OrderPhoto.fromJson(p)],
    events: [for (final e in j['events'] as List) OrderEvent.fromJson(e)],
    materials: [
      for (final m in j['materials'] as List)
        UsedMaterial(
          name: m['material_name'],
          quantity: (m['quantity'] as num).toDouble(),
          unit: m['unit'],
        ),
    ],
    aiReport: j['ai_report'] == null ? null : AiReport.fromJson(j['ai_report']),
  );
}
