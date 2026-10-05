enum Role {
  master('Мастер смены'),
  executor('Исполнитель'),
  manager('Руководитель'),
  admin('Администратор');

  const Role(this.label);
  final String label;

  static Role parse(String value) => Role.values.byName(value);
}

class AppUser {
  const AppUser({
    required this.id,
    required this.login,
    required this.fio,
    required this.role,
    this.specialty,
    this.grade,
    this.brigadeId,
    this.onShift = false,
    this.hasPin = false,
  });

  final int id;
  final String login;
  final String fio;
  final Role role;
  final String? specialty;
  final int? grade;
  final int? brigadeId;
  final bool onShift;
  final bool hasPin;

  factory AppUser.fromJson(Map<String, dynamic> j) => AppUser(
    id: j['id'],
    login: j['login'],
    fio: j['fio'],
    role: Role.parse(j['role']),
    specialty: j['specialty'],
    grade: j['grade'],
    brigadeId: j['brigade_id'],
    onShift: j['on_shift'] ?? false,
    hasPin: j['has_pin'] ?? false,
  );

  AppUser copyWith({bool? onShift}) => AppUser(
    id: id,
    login: login,
    fio: fio,
    role: role,
    specialty: specialty,
    grade: grade,
    brigadeId: brigadeId,
    onShift: onShift ?? this.onShift,
    hasPin: hasPin,
  );

  /// «Иванов С.Н.»
  String get shortName {
    final parts = fio.split(' ');
    if (parts.length < 3) return fio;
    return '${parts[0]} ${parts[1][0]}.${parts[2][0]}.';
  }
}
