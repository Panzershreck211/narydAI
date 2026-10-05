import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_client.dart';
import '../../../core/widgets/common.dart';
import '../../auth/application/auth_controller.dart';
import '../../orders/application/orders_providers.dart';

final ratingsProvider = FutureProvider.autoDispose<List<Map<String, dynamic>>>((
  ref,
) async {
  final res = await ref.watch(dioProvider).get('/analytics/ratings');
  return (res.data as List).cast<Map<String, dynamic>>();
});

final downtimeProvider = FutureProvider.autoDispose<List<Map<String, dynamic>>>(
  (ref) async {
    final res = await ref.watch(dioProvider).get('/analytics/downtime');
    return (res.data as List).cast<Map<String, dynamic>>();
  },
);

/// Руководитель: счётчики, рейтинг исполнителей, простои оборудования.
class AnalyticsScreen extends ConsumerWidget {
  const AnalyticsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final counters = ref.watch(countersProvider).asData?.value ?? const {};
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Аналитика'),
          actions: [
            IconButton(
              icon: const Icon(Icons.logout),
              onPressed: () =>
                  ref.read(authControllerProvider.notifier).logout(),
            ),
          ],
          bottom: const TabBar(
            tabs: [
              Tab(text: 'Рейтинг'),
              Tab(text: 'Простои'),
            ],
          ),
        ),
        body: Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(12),
              child: Text(
                'Смена: выдано ${counters['issued'] ?? '–'} · выполнено ${counters['completed'] ?? '–'} · '
                'просрочено ${counters['overdue'] ?? '–'} · в простое ${counters['equipment_down'] ?? '–'}',
              ),
            ),
            Expanded(
              child: TabBarView(
                children: [
                  AsyncView(
                    value: ref.watch(ratingsProvider),
                    data: (rows) => ListView(
                      children: [
                        for (final r in rows)
                          ListTile(
                            leading: CircleAvatar(child: Text('${r['rank']}')),
                            title: Text(r['fio']),
                            subtitle: Text(
                              'Закрыто ${r['closed']} · в срок ${r['on_time_pct']}% · '
                              'качество ${r['avg_quality'] ?? '–'} · отказов ${r['rejects']}',
                            ),
                            trailing: Text(
                              '${r['points']}',
                              style: Theme.of(context).textTheme.titleLarge,
                            ),
                          ),
                      ],
                    ),
                  ),
                  AsyncView(
                    value: ref.watch(downtimeProvider),
                    data: (rows) => ListView(
                      children: [
                        for (final r in rows)
                          ListTile(
                            leading: Icon(
                              Icons.precision_manufacturing,
                              color: r['still_down'] == true
                                  ? Colors.red
                                  : null,
                            ),
                            title: Text(
                              '${r['equipment']} (${r['inventory_number']})',
                            ),
                            subtitle: Text(
                              'Нарядов: ${r['orders']}${r['still_down'] == true ? ' · СЕЙЧАС В ПРОСТОЕ' : ''}',
                            ),
                            trailing: Text('${r['downtime_hours']} ч'),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
