import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/common.dart';
import '../../auth/application/auth_controller.dart';
import '../application/orders_providers.dart';
import '../domain/work_order.dart';
import 'widgets/order_card.dart';

/// Главный экран исполнителя: счётчики, отметка смены, активные и выполненные наряды.
class MyOrdersScreen extends ConsumerWidget {
  const MyOrdersScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(currentUserProvider);
    final orders = ref.watch(myOrdersProvider);
    final c = context.colors;

    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          titleSpacing: 16,
          title: BrandMark(
            subtitle: user == null
                ? null
                : '${user.shortName} · ${user.specialty ?? 'исполнитель'}',
          ),
          actions: [
            IconButton(
              tooltip: 'Уведомления',
              icon: const Icon(Icons.notifications_outlined),
              onPressed: () => context.push('/notifications'),
            ),
            IconButton(
              tooltip: 'Выйти',
              icon: const Icon(Icons.logout),
              onPressed: () =>
                  ref.read(authControllerProvider.notifier).logout(),
            ),
          ],
        ),
        body: Column(
          children: [
            _ShiftBar(onShift: user?.onShift ?? false),
            switch (orders) {
              AsyncValue(:final value?) => _Stats(value),
              _ => const SizedBox.shrink(),
            },
            Container(
              color: c.bg,
              child: const TabBar(
                tabs: [
                  Tab(text: 'Активные'),
                  Tab(text: 'Выполненные'),
                ],
              ),
            ),
            Expanded(
              child: AsyncView(
                value: orders,
                onRetry: () => ref.invalidate(myOrdersProvider),
                data: (list) {
                  final active = list.where((o) => o.status.isActive).toList();
                  final done = list.where((o) => !o.status.isActive).toList();
                  return TabBarView(
                    children: [_OrdersList(active), _OrdersList(done)],
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Плашка смены — как карточка исполнителя на доске панели (цветная точка + статус).
class _ShiftBar extends ConsumerWidget {
  const _ShiftBar({required this.onShift});
  final bool onShift;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    return Container(
      margin: const EdgeInsets.fromLTRB(12, 12, 12, 0),
      padding: const EdgeInsets.fromLTRB(14, 4, 6, 4),
      decoration: BoxDecoration(
        color: c.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: c.border),
      ),
      child: Row(
        children: [
          Container(
            width: 10,
            height: 10,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: onShift ? const Color(0xFF43A047) : c.grey,
              boxShadow: onShift
                  ? [
                      BoxShadow(
                        color: const Color(0xFF43A047).withValues(alpha: 0.35),
                        spreadRadius: 3,
                      ),
                    ]
                  : null,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              onShift ? 'На смене — наряды приходят вам' : 'Не на смене',
              style: TextStyle(
                color: onShift ? c.text : c.muted,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
          Switch(
            value: onShift,
            onChanged: (v) => ref
                .read(authControllerProvider.notifier)
                .setShift(v)
                .catchError(
                  (Object e) => context.mounted ? showError(context, e) : null,
                ),
          ),
        ],
      ),
    );
  }
}

/// Счётчики — как .stat в панели: цветная полоса слева.
class _Stats extends StatelessWidget {
  const _Stats(this.orders);
  final List<WorkOrder> orders;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final active = orders.where((o) => o.status.isActive).toList();
    Widget stat(String label, int value, Color accent, {bool alarm = false}) =>
        Expanded(
          child: Container(
            margin: const EdgeInsets.symmetric(horizontal: 4),
            decoration: BoxDecoration(
              color: c.surface,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: c.border),
            ),
            clipBehavior: Clip.antiAlias,
            child: IntrinsicHeight(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Container(width: 4, color: accent),
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(10, 8, 6, 8),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '$value',
                            style: TextStyle(
                              fontSize: 22,
                              fontWeight: FontWeight.w700,
                              color: alarm && value > 0 ? c.red : c.text,
                            ),
                          ),
                          Text(
                            label,
                            style: TextStyle(fontSize: 11.5, color: c.muted),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );

    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 10, 8, 4),
      child: Row(
        children: [
          stat('Активные', active.length, c.grey),
          stat(
            'В работе',
            active.where((o) => o.status == OrderStatus.inProgress).length,
            c.amber,
          ),
          stat(
            'Просрочено',
            active.where((o) => o.isOverdue).length,
            c.red,
            alarm: true,
          ),
        ],
      ),
    );
  }
}

class _OrdersList extends ConsumerWidget {
  const _OrdersList(this.orders);
  final List<WorkOrder> orders;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    return RefreshIndicator(
      onRefresh: () => ref.refresh(myOrdersProvider.future),
      child: orders.isEmpty
          ? ListView(
              children: [
                const SizedBox(height: 100),
                Icon(Icons.inbox_outlined, size: 40, color: c.muted),
                const SizedBox(height: 8),
                Center(
                  child: Text('Нарядов нет', style: TextStyle(color: c.muted)),
                ),
              ],
            )
          : ListView.builder(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 16),
              itemCount: orders.length,
              itemBuilder: (_, i) => OrderCard(
                order: orders[i],
                onTap: () => context.push('/orders/${orders[i].id}'),
              ),
            ),
    );
  }
}
