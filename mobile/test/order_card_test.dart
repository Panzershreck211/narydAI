import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:naryad_ai/core/theme/app_theme.dart';
import 'package:naryad_ai/features/orders/domain/work_order.dart';
import 'package:naryad_ai/features/orders/presentation/widgets/order_card.dart';

WorkOrder _order({
  String type = 'planned',
  bool overdue = false,
  String status = 'issued',
  Map<String, dynamic>? executor,
}) => WorkOrder.fromJson({
  'id': 3,
  'number': 'НР-2026-000003',
  'type': type,
  'description': 'Насос ГрАТ: течь по сальнику',
  'workshop': {'id': 1, 'name': 'ОФ №1'},
  'equipment': {'id': 2, 'name': 'Насос ГрАТ 1400/40'},
  'executor': executor ?? {'id': 4, 'fio': 'Иванов Сергей Николаевич'},
  'master': {'id': 2, 'fio': 'Ахметов Ерлан Серикович'},
  'priority': 'high',
  'deadline': DateTime.now()
      .add(Duration(hours: overdue ? -1 : 3))
      .toUtc()
      .toIso8601String(),
  'status': status,
  'is_overdue': overdue,
  'equipment_stopped': false,
  'created_at': '2026-10-05T10:00:00Z',
  'allowed_actions': ['accept'],
});

Future<void> _pump(
  WidgetTester tester,
  WorkOrder order, {
  VoidCallback? onTap,
}) => tester.pumpWidget(
  MaterialApp(
    theme: AppTheme.dark(),
    home: Scaffold(
      body: OrderCard(order: order, onTap: onTap),
    ),
  ),
);

void main() {
  setUpAll(() => initializeDateFormatting('ru'));

  testWidgets('плановый наряд: номер, статус, приоритет, без аварийной метки', (
    tester,
  ) async {
    await _pump(tester, _order());
    expect(find.text('НР-2026-000003'), findsOneWidget);
    expect(find.text('Выдан'), findsOneWidget);
    expect(find.text('Высокий'), findsOneWidget);
    expect(find.text('АВАРИЙНЫЙ'), findsNothing);
    expect(find.textContaining('просрочен'), findsNothing);
  });

  testWidgets('аварийный и просроченный наряд выделен как в панели', (
    tester,
  ) async {
    await _pump(tester, _order(type: 'emergency', overdue: true));
    expect(find.text('АВАРИЙНЫЙ'), findsOneWidget);
    // срок в прошлом — отсчёт «просрочен на …» красным
    final late = tester.widget<Text>(find.textContaining('просрочен на'));
    expect(late.style?.color, AppColors.dark.red);
    // красная полоса слева шириной 4
    final strip = find.byWidgetPredicate(
      (w) =>
          w is Container &&
          w.color == AppColors.dark.red &&
          w.constraints?.maxWidth == 4,
    );
    expect(strip, findsOneWidget);
  });

  testWidgets('у завершённых и отменённых нарядов нет обратного отсчёта', (
    tester,
  ) async {
    for (final status in ['completed', 'closed', 'cancelled', 'rejected']) {
      await _pump(tester, _order(status: status));
      expect(find.textContaining('осталось'), findsNothing, reason: status);
      expect(find.textContaining('до '), findsOneWidget, reason: status);
    }
  });

  testWidgets('тап открывает наряд', (tester) async {
    var tapped = 0;
    await _pump(tester, _order(), onTap: () => tapped++);
    await tester.tap(find.byType(OrderCard));
    expect(tapped, 1);
  });

  test('статусы бэкенда парсятся, включая in_progress', () {
    for (final s in [
      'issued',
      'accepted',
      'queued',
      'in_progress',
      'paused',
      'completed',
      'closed',
      'rejected',
      'cancelled',
    ]) {
      expect(OrderStatus.parse(s).label, isNotEmpty);
    }
    expect(OrderStatus.parse('in_progress'), OrderStatus.inProgress);
    expect(OrderStatus.inProgress.isActive, isTrue);
    expect(OrderStatus.closed.isActive, isFalse);
  });
}
