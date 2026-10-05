import 'package:flutter_test/flutter_test.dart';
import 'package:naryad_ai/features/orders/domain/work_order.dart';

void main() {
  final json = {
    'id': 7,
    'number': 'НР-2026-000007',
    'type': 'emergency',
    'description': 'Течь масла',
    'workshop': {'id': 1, 'name': 'Карьер'},
    'equipment': {
      'id': 2,
      'name': 'ЭКГ-10',
      'inventory_number': 'КМ-0103',
      'workshop_id': 1,
      'criticality': 'A',
    },
    'executor': {
      'id': 4,
      'fio': 'Иванов Сергей Николаевич',
      'specialty': 'Слесарь',
      'grade': 5,
    },
    'brigade_id': null,
    'master': {'id': 2, 'fio': 'Ахметов Ерлан Серикович'},
    'priority': 'critical',
    'deadline': '2026-10-05T12:00:00Z',
    'status': 'in_progress',
    'is_overdue': true,
    'equipment_stopped': true,
    'created_at': '2026-10-05T10:00:00Z',
    'started_at': null,
    'completed_at': null,
    'closed_at': null,
    'master_score': null,
    'allowed_actions': ['pause', 'complete', 'return', 'unknown_future_action'],
    'work_report': null,
    'fault_code': null,
    'events': [
      {
        'id': 1,
        'action': 'create',
        'from_status': null,
        'to_status': 'issued',
        'reason': null,
        'timestamp': '2026-10-05T10:00:00Z',
        'user': {'id': 2, 'fio': 'Ахметов Ерлан Серикович'},
      },
    ],
    'photos': [
      {
        'id': 1,
        'type': 'after',
        'url': '/media/orders/7/a.jpg',
        'meta': null,
        'created_at': '2026-10-05T11:00:00Z',
      },
    ],
    'materials': [],
    'ai_report': {
      'id': 1,
      'verdict': 'needs_review',
      'score': 3.6,
      'photo_score': 4.0,
      'explanation': '...',
      'checks': [
        {'name': 'relevance', 'severity': 'warn', 'message': 'слабо связан'},
      ],
      'source': 'rules',
      'created_at': '2026-10-05T11:00:00Z',
    },
  };

  test('OrderDetail parses backend payload', () {
    final d = OrderDetail.fromJson(json);
    expect(d.order.status, OrderStatus.inProgress);
    expect(d.order.isEmergency, isTrue);
    expect(d.order.isOverdue, isTrue);
    expect(d.order.allowedActions, [
      OrderAction.pause,
      OrderAction.complete,
      OrderAction.returnBack,
    ]);
    expect(d.photos.single.isAfter, isTrue);
    expect(d.aiReport!.verdictLabel, 'Нужна проверка');
    expect(d.events.single.toStatus, OrderStatus.issued);
  });

  test('return action maps to API name', () {
    expect(OrderAction.returnBack.apiName, 'return');
  });
}
