-- ============================================================================
-- ALGO V1 — СКЕЛЕТ 6 КЛАСС (чистый методический файл)
-- Источник: Sardor Bozorov, PDF программа 6 класса
-- 2 раздела, 9 тем, 47 пунктов, 159 атомарных навыков
-- ============================================================================
-- ФОРМАТ: Только поля методиста. ИИ-поля (importance, typical_time_seconds,
-- irt_*, difficulty_score, weight, criticality) заполняются пайплайном.
-- Prerequisites — будут сгенерированы AI-пайплайном
-- ============================================================================

-- Очистка
DELETE FROM tasks_master WHERE skill_id LIKE 'G6_%';
DELETE FROM knowledge_hierarchy WHERE id LIKE 'G6_%';

-- ============================================================================
-- L1: РАЗДЕЛЫ (2)
-- ============================================================================
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, class_level_start, class_level_end, sequence_order)
VALUES
    ('G6_FRAC', 'L1', NULL, 'Common Fractions',    'Обыкновенные дроби',   6, 6, 1),
    ('G6_RAT',  'L1', NULL, 'Rational Numbers',     'Рациональные числа',  6, 6, 2);

-- ============================================================================
-- L2: ТЕМЫ (9)
-- ============================================================================
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, class_level_start, class_level_end, sequence_order)
VALUES
    ('G6_T01', 'L2', 'G6_FRAC', 'Divisibility',                                          'Делимость чисел',                                                      6, 6, 1),
    ('G6_T02', 'L2', 'G6_FRAC', 'Add Sub Fractions with Different Denominators',          'Сложение и вычитание дробей с разными знаменателями',                   6, 6, 2),
    ('G6_T03', 'L2', 'G6_FRAC', 'Mul Div Common Fractions',                               'Умножение и деление обыкновенных дробей',                               6, 6, 3),
    ('G6_T04', 'L2', 'G6_FRAC', 'Ratios and Proportions',                                 'Отношения и пропорции',                                                6, 6, 4),
    ('G6_T05', 'L2', 'G6_RAT',  'Positive and Negative Numbers',                          'Положительные и отрицательные числа',                                   6, 6, 5),
    ('G6_T06', 'L2', 'G6_RAT',  'Add Sub Positive and Negative Numbers',                  'Сложение и вычитание положительных и отрицательных чисел',              6, 6, 6),
    ('G6_T07', 'L2', 'G6_RAT',  'Mul Div Positive and Negative Numbers',                  'Умножение и деление положительных и отрицательных чисел',               6, 6, 7),
    ('G6_T08', 'L2', 'G6_RAT',  'Solving Equations',                                      'Решение уравнений',                                                    6, 6, 8),
    ('G6_T09', 'L2', 'G6_RAT',  'Coordinates on the Plane',                               'Координаты на плоскости',                                              6, 6, 9);

-- ============================================================================
-- L3: ПУНКТЫ (47)
-- ============================================================================
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, class_level_start, class_level_end, sequence_order)
VALUES
    -- Тема 1: Делимость чисел
    ('G6_P01', 'L3', 'G6_T01', 'Divisors and Multiples',                'Делители и кратные',                                    6, 6,  1),
    ('G6_P02', 'L3', 'G6_T01', 'Divisibility by 10 5 2',               'Признаки делимости на 10, 5, 2',                        6, 6,  2),
    ('G6_P03', 'L3', 'G6_T01', 'Divisibility by 9 and 3',              'Признаки делимости на 9 и 3',                           6, 6,  3),
    ('G6_P04', 'L3', 'G6_T01', 'Prime and Composite Numbers',          'Простые и составные числа',                             6, 6,  4),
    ('G6_P05', 'L3', 'G6_T01', 'Prime Factorization',                  'Разложение на простые множители',                       6, 6,  5),
    ('G6_P06', 'L3', 'G6_T01', 'GCD Coprime Numbers',                  'НОД. Взаимно простые числа',                            6, 6,  6),
    ('G6_P07', 'L3', 'G6_T01', 'LCM',                                  'НОК',                                                   6, 6,  7),
    -- Тема 2: Сложение и вычитание дробей с разными знаменателями
    ('G6_P08', 'L3', 'G6_T02', 'Fundamental Property of Fractions',    'Основное свойство дроби',                               6, 6,  8),
    ('G6_P09', 'L3', 'G6_T02', 'Reducing Fractions',                   'Сокращение дробей',                                     6, 6,  9),
    ('G6_P10', 'L3', 'G6_T02', 'Common Denominator',                   'Приведение к общему знаменателю',                       6, 6, 10),
    ('G6_P11', 'L3', 'G6_T02', 'Compare Add Sub Different Denom',      'Сравнение, сложение и вычитание дробей с разными знаменателями', 6, 6, 11),
    ('G6_P12', 'L3', 'G6_T02', 'Add Sub Mixed Numbers',                'Сложение и вычитание смешанных чисел',                  6, 6, 12),
    -- Тема 3: Умножение и деление обыкновенных дробей
    ('G6_P13', 'L3', 'G6_T03', 'Multiplying Fractions',                'Умножение дробей',                                      6, 6, 13),
    ('G6_P14', 'L3', 'G6_T03', 'Fraction of a Number',                 'Нахождение дроби от числа',                             6, 6, 14),
    ('G6_P15', 'L3', 'G6_T03', 'Distributive Property of Mul',         'Распределительное свойство умножения',                  6, 6, 15),
    ('G6_P16', 'L3', 'G6_T03', 'Reciprocal Numbers',                   'Взаимно обратные числа',                                6, 6, 16),
    ('G6_P17', 'L3', 'G6_T03', 'Dividing Fractions',                   'Деление дробей',                                        6, 6, 17),
    ('G6_P18', 'L3', 'G6_T03', 'Number from its Fraction',             'Нахождение числа по его дроби',                         6, 6, 18),
    ('G6_P19', 'L3', 'G6_T03', 'Fractional Expressions',               'Дробные выражения',                                     6, 6, 19),
    -- Тема 4: Отношения и пропорции
    ('G6_P20', 'L3', 'G6_T04', 'Ratios',                               'Отношения',                                             6, 6, 20),
    ('G6_P21', 'L3', 'G6_T04', 'Proportions',                          'Пропорции',                                             6, 6, 21),
    ('G6_P22', 'L3', 'G6_T04', 'Direct and Inverse Proportionality',   'Прямая и обратная пропорциональные зависимости',         6, 6, 22),
    ('G6_P23', 'L3', 'G6_T04', 'Scale',                                'Масштаб',                                               6, 6, 23),
    ('G6_P24', 'L3', 'G6_T04', 'Circumference and Circle Area',        'Длина окружности и площадь круга',                      6, 6, 24),
    ('G6_P25', 'L3', 'G6_T04', 'Sphere',                               'Шар',                                                   6, 6, 25),
    -- Тема 5: Положительные и отрицательные числа
    ('G6_P26', 'L3', 'G6_T05', 'Coordinates on a Line',                'Координаты на прямой',                                  6, 6, 26),
    ('G6_P27', 'L3', 'G6_T05', 'Opposite Numbers',                     'Противоположные числа',                                 6, 6, 27),
    ('G6_P28', 'L3', 'G6_T05', 'Absolute Value',                       'Модуль числа',                                          6, 6, 28),
    ('G6_P29', 'L3', 'G6_T05', 'Comparing Numbers',                    'Сравнение чисел',                                       6, 6, 29),
    ('G6_P30', 'L3', 'G6_T05', 'Change of Quantities',                 'Изменение величин',                                     6, 6, 30),
    -- Тема 6: Сложение и вычитание положительных и отрицательных чисел
    ('G6_P31', 'L3', 'G6_T06', 'Addition on Number Line',              'Сложение чисел с помощью координатной прямой',           6, 6, 31),
    ('G6_P32', 'L3', 'G6_T06', 'Adding Negative Numbers',              'Сложение отрицательных чисел',                          6, 6, 32),
    ('G6_P33', 'L3', 'G6_T06', 'Adding Numbers with Different Signs',  'Сложение чисел с разными знаками',                      6, 6, 33),
    ('G6_P34', 'L3', 'G6_T06', 'Subtraction',                          'Вычитание',                                             6, 6, 34),
    -- Тема 7: Умножение и деление положительных и отрицательных чисел
    ('G6_P35', 'L3', 'G6_T07', 'Multiplication',                       'Умножение',                                             6, 6, 35),
    ('G6_P36', 'L3', 'G6_T07', 'Division',                             'Деление',                                               6, 6, 36),
    ('G6_P37', 'L3', 'G6_T07', 'Rational Numbers',                     'Рациональные числа',                                    6, 6, 37),
    ('G6_P38', 'L3', 'G6_T07', 'Properties of Rational Operations',    'Свойства действий с рациональными числами',              6, 6, 38),
    -- Тема 8: Решение уравнений
    ('G6_P39', 'L3', 'G6_T08', 'Expanding Brackets',                   'Раскрытие скобок',                                      6, 6, 39),
    ('G6_P40', 'L3', 'G6_T08', 'Coefficient',                          'Коэффициент',                                           6, 6, 40),
    ('G6_P41', 'L3', 'G6_T08', 'Like Terms',                           'Подобные слагаемые',                                    6, 6, 41),
    ('G6_P42', 'L3', 'G6_T08', 'Solving Equations',                    'Решение уравнений',                                     6, 6, 42),
    -- Тема 9: Координаты на плоскости
    ('G6_P43', 'L3', 'G6_T09', 'Perpendicular Lines',                  'Перпендикулярные прямые',                               6, 6, 43),
    ('G6_P44', 'L3', 'G6_T09', 'Parallel Lines',                       'Параллельные прямые',                                   6, 6, 44),
    ('G6_P45', 'L3', 'G6_T09', 'Coordinate Plane',                     'Координатная плоскость',                                6, 6, 45),
    ('G6_P46', 'L3', 'G6_T09', 'Bar Charts',                           'Столбчатые диаграммы',                                  6, 6, 46),
    ('G6_P47', 'L3', 'G6_T09', 'Graphs',                               'Графики',                                               6, 6, 47);

-- ============================================================================
-- L4: АТОМАРНЫЕ НАВЫКИ (159)
-- Каждый навык содержит: example_task, assessed_ability, difficulty_level, formula из PDF
-- ============================================================================

-- ─── П.1: Делители и кратные (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S01_01','L4','G6_P01','Find divisors of a number','Нахождение делителей числа','Определение чисел, на которые делится без остатка',1,'apply',6,6,
 'Найдите все делители числа 18','Определение чисел, на которые делится без остатка','Low (Level A)',NULL),
('G6_S01_02','L4','G6_P01','Find multiples of a number','Нахождение кратных числа','Использование формулы кратного: a × n',2,'apply',6,6,
 'Запишите первые пять кратных числа 6','Использование формулы кратного: a × n','Low (Level A)','Кратное числа a: a × n, где n — натуральное'),
('G6_S01_03','L4','G6_P01','Check divisibility','Проверка делимости','Проверка деления без остатка',3,'apply',6,6,
 'Является ли число 4 делителем 28','Проверка деления без остатка','Medium (Level B)',NULL);

-- ─── П.2: Признаки делимости на 10, 5, 2 (4 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S02_01','L4','G6_P02','Divisibility by 10','Делимость на 10','Правило: последняя цифра 0',1,'recall',6,6,
 'Делится ли 450 на 10','Правило: последняя цифра 0','Low (Level A)','Делимость на 10: последняя цифра 0'),
('G6_S02_02','L4','G6_P02','Divisibility by 5','Делимость на 5','Правило: последняя цифра 0 или 5',2,'recall',6,6,
 'Делится ли 235 на 5','Правило: последняя цифра 0 или 5','Low (Level A)','Делимость на 5: последняя цифра 0 или 5'),
('G6_S02_03','L4','G6_P02','Divisibility by 2','Делимость на 2','Правило: последняя цифра четная',3,'recall',6,6,
 'Делится ли 346 на 2','Правило: последняя цифра четная','Low (Level A)','Делимость на 2: последняя цифра чётная'),
('G6_S02_04','L4','G6_P02','Apply multiple divisibility rules','Применение нескольких признаков','Анализ последней цифры',4,'analyze',6,6,
 'Делится ли 540 на 2 и на 5','Анализ последней цифры','Medium (Level B)',NULL);

-- ─── П.3: Признаки делимости на 9 и 3 (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S03_01','L4','G6_P03','Divisibility by 3','Делимость на 3','Сумма цифр делится на 3',1,'apply',6,6,
 'Делится ли 123 на 3','Сумма цифр делится на 3','Medium (Level B)','Делимость на 3: сумма цифр делится на 3'),
('G6_S03_02','L4','G6_P03','Divisibility by 9','Делимость на 9','Сумма цифр делится на 9',2,'apply',6,6,
 'Делится ли 729 на 9','Сумма цифр делится на 9','Medium (Level B)','Делимость на 9: сумма цифр делится на 9'),
('G6_S03_03','L4','G6_P03','Divisibility by 3 for large numbers','Делимость на 3 для больших чисел','Быстрый подсчет суммы цифр',3,'apply',6,6,
 'Делится ли 54837 на 3','Быстрый подсчет суммы цифр','Medium (Level B)',NULL);

-- ─── П.4: Простые и составные числа (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S04_01','L4','G6_P04','Identify prime number','Определение простого числа','Число имеет ровно 2 делителя',1,'recall',6,6,
 'Является ли 17 простым числом','Число имеет ровно 2 делителя','Low (Level A)',NULL),
('G6_S04_02','L4','G6_P04','Identify composite number','Определение составного числа','Поиск делителей кроме 1 и самого числа',2,'recall',6,6,
 'Является ли 21 составным','Поиск делителей кроме 1 и самого числа','Low (Level A)',NULL),
('G6_S04_03','L4','G6_P04','Classify prime from list','Выделение простых из списка','Анализ делителей',3,'analyze',6,6,
 'Какие числа из списка 2, 9, 11, 15 являются простыми','Анализ делителей','Medium (Level B)',NULL);

-- ─── П.5: Разложение на простые множители (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S05_01','L4','G6_P05','Factorize prime number','Разложение простого числа','Запись 13 = 13',1,'recall',6,6,
 'Разложите 13','Запись 13 = 13','Low (Level A)',NULL),
('G6_S05_02','L4','G6_P05','Prime factorization','Разложение на простые множители','Представление числа в виде произведения простых',2,'apply',6,6,
 'Разложите 24 на простые множители','Представление 24 = 2 × 2 × 2 × 3','Medium (Level B)',NULL),
('G6_S05_03','L4','G6_P05','Prime power factorization','Запись в виде произведения степеней','36 = 2² × 3²',3,'apply',6,6,
 'Запишите 36 в виде произведения простых степеней','36 = 2² × 3²','Medium (Level B)',NULL);

-- ─── П.6: НОД. Взаимно простые числа (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S06_01','L4','G6_P06','Find GCD','Нахождение НОД','Выбор наибольшего общего делителя',1,'apply',6,6,
 'Найдите НОД(12; 18)','Выбор наибольшего общего делителя','Medium (Level B)',NULL),
('G6_S06_02','L4','G6_P06','GCD via prime factorization','НОД через разложение','Использование разложения на простые множители',2,'apply',6,6,
 'Найдите НОД(24; 36)','Использование разложения на простые множители','Medium (Level B)',NULL),
('G6_S06_03','L4','G6_P06','Check coprime numbers','Проверка взаимной простоты','Проверка НОД = 1',3,'apply',6,6,
 'Являются ли 8 и 15 взаимно простыми','Проверка НОД = 1','Medium (Level B)',NULL);

-- ─── П.7: НОК (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S07_01','L4','G6_P07','Find LCM','Нахождение НОК','Поиск наименьшего общего кратного',1,'apply',6,6,
 'Найдите НОК(4; 6)','Поиск наименьшего общего кратного','Medium (Level B)',NULL),
('G6_S07_02','L4','G6_P07','LCM via prime factorization','НОК через разложение','Берутся наибольшие степени простых множителей',2,'apply',6,6,
 'Найдите НОК(12; 18)','Берутся наибольшие степени простых множителей','High (Level C)',NULL),
('G6_S07_03','L4','G6_P07','GCD LCM formula','Формула НОД×НОК','Применение формулы',3,'apply',6,6,
 'Проверьте формулу НОД(a; b) × НОК(a; b) = a × b для 6 и 8','Применение формулы','High (Level C)','НОД(a,b) × НОК(a,b) = a × b');

-- ─── П.8: Основное свойство дроби (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S08_01','L4','G6_P08','Expand fraction','Расширение дроби','Применение формулы a/b = a×k/b×k',1,'apply',6,6,
 'Представьте дробь 2/5 со знаменателем 15','Применение формулы a/b = a×k/b×k','Low (Level A)','a/b = (a×k)/(b×k) — основное свойство дроби'),
('G6_S08_02','L4','G6_P08','Reduce fraction','Преобразование дроби делением','Деление числителя и знаменателя на одно число',2,'apply',6,6,
 'Получите дробь 3/4 из дроби 9/12','Деление числителя и знаменателя на одно число','Medium (Level B)',NULL),
('G6_S08_03','L4','G6_P08','Check fraction equality','Проверка равенства дробей','Применение основного свойства дроби',3,'apply',6,6,
 'Равны ли дроби 4/6 и 2/3','Применение основного свойства дроби','Medium (Level B)',NULL);

-- ─── П.9: Сокращение дробей (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S09_01','L4','G6_P09','Reduce fraction by GCD','Сокращение дроби','Деление на НОД',1,'apply',6,6,
 'Сократите 8/12','Деление на НОД','Medium (Level B)',NULL),
('G6_S09_02','L4','G6_P09','Reduce fraction fully','Полное сокращение дроби','Нахождение НОД и деление на него',2,'apply',6,6,
 'Сократите 18/24 полностью','Нахождение НОД и деление на него','Medium (Level B)',NULL),
('G6_S09_03','L4','G6_P09','Irreducible fraction check','Проверка несократимости','Понимание взаимно простых чисел',3,'recall',6,6,
 'Можно ли сократить 5/7','Понимание взаимно простых чисел','Low (Level A)',NULL);

-- ─── П.10: Приведение к общему знаменателю (4 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S10_01','L4','G6_P10','Common denominator via LCM','Общий знаменатель через НОК','Нахождение НОК(4;6)',1,'apply',6,6,
 'Приведите 1/4 и 1/6 к общему знаменателю','Нахождение НОК(4;6)','Medium (Level B)','НОК знаменателей — общий знаменатель'),
('G6_S10_02','L4','G6_P10','Common denominator with expansion','Приведение с расширением','Применение основного свойства дроби',2,'apply',6,6,
 'Приведите 3/8 и 5/12 к общему знаменателю','Применение основного свойства дроби','Medium (Level B)',NULL),
('G6_S10_03','L4','G6_P10','Prepare fractions for addition','Подготовка дробей к сложению','Приведение к знаменателю 9',3,'apply',6,6,
 'Подготовьте дроби 2/3 и 5/9 к сложению','Приведение к знаменателю 9','Medium (Level B)',NULL),
('G6_S10_04','L4','G6_P10','Choose convenient denominator','Выбор удобного знаменателя','Анализ кратных',4,'analyze',6,6,
 'Какой общий знаменатель удобнее для 2/5 и 3/10','Анализ кратных','High (Level C)',NULL);

-- ─── П.11: Сравнение, сложение и вычитание дробей с разными знаменателями (6 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S11_01','L4','G6_P11','Compare fractions via LCM','Сравнение дробей через НОК','Нахождение НОК(3;5)',1,'apply',6,6,
 'Сравните 2/3 и 3/5','Нахождение НОК(3;5)','Medium (Level B)',NULL),
('G6_S11_02','L4','G6_P11','Compare fractions cross multiply','Сравнение дробей перекрёстным умножением','Применение перекрестного умножения',2,'apply',6,6,
 'Сравните 4/7 и 5/9','Применение перекрестного умножения','High (Level C)',NULL),
('G6_S11_03','L4','G6_P11','Add fractions different denom','Сложение дробей с разными знаменателями','Нахождение НОК и приведение',3,'apply',6,6,
 '1/4 + 1/6','Нахождение НОК и приведение','Medium (Level B)',NULL),
('G6_S11_04','L4','G6_P11','Add fractions simplify result','Сложение дробей с упрощением','Упрощение результата',4,'apply',6,6,
 '2/5 + 3/10','Упрощение результата','Medium (Level B)',NULL),
('G6_S11_05','L4','G6_P11','Subtract fractions different denom','Вычитание дробей с разными знаменателями','Приведение к общему знаменателю',5,'apply',6,6,
 '5/6 − 1/4','Приведение к общему знаменателю','Medium (Level B)',NULL),
('G6_S11_06','L4','G6_P11','Subtract fractions negative result','Вычитание дробей с отрицательным результатом','Работа с отрицательной дробью',6,'apply',6,6,
 '2/5 − 3/4','Работа с отрицательной дробью','High (Level C)',NULL);

-- ─── П.12: Сложение и вычитание смешанных чисел (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S12_01','L4','G6_P12','Add mixed numbers same denom','Сложение смешанных чисел с одинаковыми знаменателями','Сложение по частям',1,'apply',6,6,
 '2 1/3 + 1 1/3','Сложение по частям','Low (Level A)',NULL),
('G6_S12_02','L4','G6_P12','Add mixed numbers with carry','Сложение смешанных чисел с выделением целой части','Выделение целой части',2,'apply',6,6,
 '3 3/5 + 2 4/5','Выделение целой части','Medium (Level B)',NULL),
('G6_S12_03','L4','G6_P12','Subtract mixed numbers same denom','Вычитание смешанных чисел с одинаковыми знаменателями','Вычитание по частям',3,'apply',6,6,
 '5 3/8 − 2 1/8','Вычитание по частям','Medium (Level B)',NULL),
('G6_S12_04','L4','G6_P12','Subtract mixed numbers with borrow','Вычитание смешанных чисел с заимствованием','Преобразование перед вычитанием',4,'apply',6,6,
 '5 1/3 − 2 2/3','Преобразование перед вычитанием','High (Level C)',NULL),
('G6_S12_05','L4','G6_P12','Add mixed numbers different denom','Сложение смешанных чисел с разными знаменателями','Приведение дробных частей к общему знаменателю',5,'apply',6,6,
 '3 1/4 + 2 2/3','Приведение дробных частей к общему знаменателю','High (Level C)',NULL);

-- ─── П.13: Умножение дробей (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S13_01','L4','G6_P13','Multiply simple fractions','Умножение простых дробей','Умножение числителей и знаменателей',1,'apply',6,6,
 '2/3 × 3/5','Умножение числителей и знаменателей','Low (Level A)','a/b × c/d = (a×c)/(b×d)'),
('G6_S13_02','L4','G6_P13','Multiply fractions with cross cancel','Умножение дробей с сокращением','Сокращение крест-накрест',2,'apply',6,6,
 '4/9 × 3/8','Сокращение крест-накрест','Medium (Level B)',NULL),
('G6_S13_03','L4','G6_P13','Multiply mixed number by fraction','Умножение смешанного числа на дробь','Перевод смешанного числа в неправильную дробь',3,'apply',6,6,
 '2 1/3 × 3/4','Перевод смешанного числа в неправильную дробь','High (Level C)','a/b : c/d = a/b × d/c');

-- ─── П.14: Нахождение дроби от числа (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S14_01','L4','G6_P14','Fraction of a whole number','Дробь от целого числа','Умножение числа на дробь',1,'apply',6,6,
 'Найдите 3/4 от 20','Умножение числа на дробь','Medium (Level B)','a × b/c = (a×b)/c'),
('G6_S14_02','L4','G6_P14','Fraction of a fraction','Дробь от дроби','Дробь от дроби',2,'apply',6,6,
 'Найдите 2/3 от 9/10','Дробь от дроби','Medium (Level B)',NULL),
('G6_S14_03','L4','G6_P14','Fraction of number word problem','Дробь от числа в задаче','Перевод условия в выражение',3,'apply',6,6,
 'В классе 24 ученика. 3/8 — девочки. Сколько девочек','Перевод условия в выражение','High (Level C)',NULL);

-- ─── П.15: Распределительное свойство умножения (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S15_01','L4','G6_P15','Apply distributive property','Применение распределительного свойства','Применение распределительного свойства',1,'apply',6,6,
 '1/2(6 + 8)','Применение распределительного свойства','Medium (Level B)','Отношение a к b: a/b или a:b'),
('G6_S15_02','L4','G6_P15','Distributive property with fractions','Распределительное свойство с дробями','Поэтапное применение формулы',2,'apply',6,6,
 '2/3(3/4 + 1/4)','Поэтапное применение формулы','Medium (Level B)',NULL),
('G6_S15_03','L4','G6_P15','Factor out common fraction','Вынесение общего множителя','Вынесение общего множителя',3,'apply',6,6,
 '3/5 × 8 + 3/5 × 2','Вынесение общего множителя','High (Level C)',NULL);

-- ─── П.16: Взаимно обратные числа (2 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S16_01','L4','G6_P16','Find reciprocal','Нахождение обратного числа','Переворот дроби',1,'apply',6,6,
 'Найдите число, обратное 4/7','Переворот дроби','Low (Level A)','a/b = c/d — пропорция'),
('G6_S16_02','L4','G6_P16','Check reciprocal pair','Проверка взаимной обратности','Проверка произведения',2,'apply',6,6,
 'Являются ли 3/5 и 5/3 взаимно обратными','Проверка произведения','Medium (Level B)',NULL);

-- ─── П.17: Деление дробей (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S17_01','L4','G6_P17','Divide fractions','Деление дробей','Умножение на обратную дробь',1,'apply',6,6,
 '2/3 : 4/5','Умножение на обратную дробь','Medium (Level B)','S = v × t'),
('G6_S17_02','L4','G6_P17','Divide mixed numbers','Деление смешанных чисел','Перевод в неправильные дроби',2,'apply',6,6,
 '1 1/2 : 3/4','Перевод в неправильные дроби','High (Level C)','C = 2πr'),
('G6_S17_03','L4','G6_P17','Divide fraction by whole number','Деление дроби на целое число','Представление целого как дроби',3,'apply',6,6,
 '5/6 : 2','Представление 2 как 2/1','Medium (Level B)','S = πr²');

-- ─── П.18: Нахождение числа по его дроби (2 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S18_01','L4','G6_P18','Find number from its fraction','Нахождение числа по его дроби','Составление выражения',1,'apply',6,6,
 '3/5 числа равны 12. Найдите число','Составление выражения','High (Level C)','d = 2r'),
('G6_S18_02','L4','G6_P18','Verify found number','Проверка найденного числа','Обратная проверка',2,'apply',6,6,
 'Проверьте найденное число','Обратная проверка','Medium (Level B)',NULL);

-- ─── П.19: Дробные выражения (2 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S19_01','L4','G6_P19','Evaluate fractional expression','Вычисление дробного выражения','Соблюдение порядка действий',1,'apply',6,6,
 '2/3 + 1/6 × 3/4','Соблюдение порядка действий','High (Level C)',NULL),
('G6_S19_02','L4','G6_P19','Evaluate compound fractional expression','Вычисление составного дробного выражения','Поэтапное применение формул',2,'apply',6,6,
 '(3/4 × 8/9) : (2/3)','Поэтапное применение формул','High (Level C)',NULL);

-- ─── П.20: Отношения (4 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S20_01','L4','G6_P20','Write ratio','Запись отношения','Запись 4:7 или 4/7',1,'apply',6,6,
 'Запишите отношение 4 к 7','Запись 4:7 или 4/7','Low (Level A)',NULL),
('G6_S20_02','L4','G6_P20','Find ratio value','Нахождение значения отношения','Деление 12:3',2,'apply',6,6,
 'Найдите отношение 12 к 3','Деление 12:3','Medium (Level B)',NULL),
('G6_S20_03','L4','G6_P20','Simplify ratio','Упрощение отношения','Деление на общий делитель',3,'apply',6,6,
 'Упростите отношение 8 : 12','Деление на общий делитель','Medium (Level B)',NULL),
('G6_S20_04','L4','G6_P20','Ratio word problem','Отношение в задаче','Перевод условия в отношение',4,'analyze',6,6,
 'В классе 10 мальчиков и 15 девочек. Найдите отношение мальчиков к девочкам','Перевод условия в отношение','High (Level C)',NULL);

-- ─── П.21: Пропорции (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S21_01','L4','G6_P21','Verify proportion','Проверка пропорции','Проверка произведений крайних и средних членов',1,'apply',6,6,
 'Верна ли пропорция 2/3 = 4/6','Проверка произведений крайних и средних членов','Medium (Level B)',NULL),
('G6_S21_02','L4','G6_P21','Solve proportion','Решение пропорции','Применение свойства ad = bc',2,'apply',6,6,
 'Найдите x из 3/5 = x/10','Применение свойства ad = bc','High (Level C)',NULL),
('G6_S21_03','L4','G6_P21','Proportion word problem','Пропорция в задаче','Построение пропорции',3,'apply',6,6,
 '5 тетрадей стоят 100 рублей. Сколько стоят 8 тетрадей','Построение пропорции','High (Level C)',NULL);

-- ─── П.22: Прямая и обратная пропорциональные зависимости (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S22_01','L4','G6_P22','Direct proportionality','Прямая пропорциональность','Понимание формулы S = vt',1,'analyze',6,6,
 'Если скорость постоянна, путь зависит от времени как','Понимание формулы S = vt','Medium (Level B)',NULL),
('G6_S22_02','L4','G6_P22','Inverse proportionality','Обратная пропорциональность','Понимание t = S/v',2,'analyze',6,6,
 'Время зависит от скорости при постоянном пути как','Понимание t = S/v','Medium (Level B)',NULL),
('G6_S22_03','L4','G6_P22','Inverse proportion problem','Задача на обратную зависимость','Применение обратной зависимости',3,'analyze',6,6,
 'Если 3 рабочих делают работу за 6 часов, за сколько часов сделают 6 рабочих','Применение обратной зависимости','High (Level C)',NULL);

-- ─── П.23: Масштаб (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S23_01','L4','G6_P23','Understand scale notation','Понимание записи масштаба','Понимание записи',1,'recall',6,6,
 'Что означает масштаб 1:100','Понимание записи','Low (Level A)',NULL),
('G6_S23_02','L4','G6_P23','Find real distance from map','Нахождение реального расстояния','Применение пропорции',2,'apply',6,6,
 'На карте 5 см, масштаб 1:1000. Найдите реальное расстояние','Применение пропорции','Medium (Level B)',NULL),
('G6_S23_03','L4','G6_P23','Find map distance from real','Нахождение расстояния на карте','Составление пропорции',3,'apply',6,6,
 'Реальное расстояние 200 м, масштаб 1:10000. Найдите расстояние на карте','Составление пропорции','High (Level C)',NULL);

-- ─── П.24: Длина окружности и площадь круга (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S24_01','L4','G6_P24','Circumference formula','Длина окружности','Подстановка в формулу C=2πr',1,'apply',6,6,
 'Найдите C при r = 5','Подстановка в формулу C=2πr','Medium (Level B)',NULL),
('G6_S24_02','L4','G6_P24','Circle area formula','Площадь круга','Вычисление квадрата радиуса S=πr²',2,'apply',6,6,
 'Найдите S при r = 3','Вычисление квадрата радиуса S=πr²','Medium (Level B)',NULL),
('G6_S24_03','L4','G6_P24','Find radius from area','Нахождение радиуса по площади','Решение уравнения r² = 25',3,'apply',6,6,
 'Площадь круга 25π. Найдите радиус','Решение уравнения r² = 25','High (Level C)',NULL);

-- ─── П.25: Шар (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S25_01','L4','G6_P25','Sphere diameter','Диаметр шара','Применение формулы d = 2r',1,'apply',6,6,
 'Найдите диаметр шара при r = 6','Применение формулы d = 2r','Low (Level A)',NULL),
('G6_S25_02','L4','G6_P25','Sphere vs circle','Отличие шара от круга','Различие плоской и пространственной фигуры',2,'recall',6,6,
 'Чем шар отличается от круга','Различие плоской и пространственной фигуры','Low (Level A)',NULL),
('G6_S25_03','L4','G6_P25','Find radius from diameter','Нахождение радиуса по диаметру','Деление диаметра на 2',3,'apply',6,6,
 'Найдите радиус мяча, если диаметр 22 см','Деление диаметра на 2','Medium (Level B)',NULL);

-- ─── П.26: Координаты на прямой (4 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S26_01','L4','G6_P26','Read coordinate on line','Определение координаты точки','Понимание направления на прямой',1,'apply',6,6,
 'Укажите координату точки, расположенной на 3 деления левее нуля','Понимание направления на прямой','Low (Level A)',NULL),
('G6_S26_02','L4','G6_P26','Plot negative number','Отметка отрицательного числа','Правильное расположение точки',2,'apply',6,6,
 'Отметьте число −4 на числовой прямой','Правильное расположение точки','Low (Level A)',NULL),
('G6_S26_03','L4','G6_P26','Distance between numbers','Расстояние между числами','Вычисление разности координат |a − b|',3,'apply',6,6,
 'Найдите расстояние между числами −2 и 3','Вычисление разности координат |a − b|','Medium (Level B)',NULL),
('G6_S26_04','L4','G6_P26','Compare negative numbers on line','Сравнение отрицательных чисел на прямой','Сравнение отрицательных чисел',4,'apply',6,6,
 'Какое число левее: −5 или −2','Сравнение отрицательных чисел','Medium (Level B)',NULL);

-- ─── П.27: Противоположные числа (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S27_01','L4','G6_P27','Find opposite number','Нахождение противоположного числа','Смена знака',1,'apply',6,6,
 'Найдите число, противоположное -7','Смена знака','Low (Level A)',NULL),
('G6_S27_02','L4','G6_P27','Check opposite pair','Проверка противоположности','Проверка суммы',2,'apply',6,6,
 'Являются ли 5 и -5 противоположными','Проверка суммы','Low (Level A)',NULL),
('G6_S27_03','L4','G6_P27','Sum of opposites','Сумма противоположных чисел','Понимание, что сумма равна 0',3,'apply',6,6,
 'Найдите сумму 8 + (-8)','Понимание, что сумма равна 0','Medium (Level B)',NULL);

-- ─── П.28: Модуль числа (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S28_01','L4','G6_P28','Absolute value of positive','Модуль положительного числа','Понимание определения',1,'apply',6,6,
 'Найдите |6|','Понимание определения','Low (Level A)',NULL),
('G6_S28_02','L4','G6_P28','Absolute value of negative','Модуль отрицательного числа','Снятие знака минус',2,'apply',6,6,
 'Найдите |-9|','Снятие знака минус','Low (Level A)',NULL),
('G6_S28_03','L4','G6_P28','Sum of absolute values','Сумма модулей','Последовательное вычисление',3,'apply',6,6,
 'Найдите |-4| + |3|','Последовательное вычисление','Medium (Level B)',NULL);

-- ─── П.29: Сравнение чисел (4 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S29_01','L4','G6_P29','Compare positive and negative','Сравнение положительного и отрицательного','Понимание расположения на прямой',1,'apply',6,6,
 'Что больше: 3 или -2','Понимание расположения на прямой','Low (Level A)',NULL),
('G6_S29_02','L4','G6_P29','Compare two negatives','Сравнение двух отрицательных','Чем ближе к нулю, тем больше',2,'apply',6,6,
 'Что больше: -3 или -7','Чем ближе к нулю, тем больше','Medium (Level B)',NULL),
('G6_S29_03','L4','G6_P29','Compare absolute values','Сравнение модулей','Сравнение |-8| и |5|',3,'apply',6,6,
 'У какого числа больше модуль: -8 или 5','Сравнение |-8| и |5|','Medium (Level B)',NULL),
('G6_S29_04','L4','G6_P29','Order numbers on line','Расположение чисел по порядку','Понимание порядка на прямой',4,'apply',6,6,
 'Расположите числа -4, 2, -1, 0','Понимание порядка на прямой','High (Level C)',NULL);

-- ─── П.30: Изменение величин (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S30_01','L4','G6_P30','Find change of quantity','Нахождение изменения величины','Вычисление разности',1,'apply',6,6,
 'Температура была 5°C, стала -3°C. Найдите изменение','Вычисление разности','Medium (Level B)','|a| = a при a≥0, |a| = −a при a<0'),
('G6_S30_02','L4','G6_P30','Interpret negative change','Интерпретация отрицательного изменения','Понимание уменьшения величины',2,'apply',6,6,
 'Что означает результат -8°C','Понимание уменьшения величины','Medium (Level B)',NULL),
('G6_S30_03','L4','G6_P30','Cumulative change','Суммарное изменение величин','Сложение положительных и отрицательных чисел',3,'apply',6,6,
 'Уровень воды изменился на -4 м, затем на +7 м. Найдите итоговое изменение','Сложение положительных и отрицательных чисел','High (Level C)',NULL);

-- ─── П.31: Сложение чисел с помощью координатной прямой (4 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S31_01','L4','G6_P31','Add positives on line','Сложение положительных на прямой','Движение вправо',1,'apply',6,6,
 'Найдите 2 + 3 на координатной прямой','Движение вправо','Low (Level A)',NULL),
('G6_S31_02','L4','G6_P31','Add positive and negative on line','Сложение с отрицательным на прямой','Движение влево',2,'apply',6,6,
 'Найдите 4 + (-5) на координатной прямой','Движение влево','Medium (Level B)',NULL),
('G6_S31_03','L4','G6_P31','Add crossing zero','Сложение с переходом через ноль','Переход через ноль',3,'apply',6,6,
 'Найдите -3 + 6','Переход через ноль','Medium (Level B)',NULL),
('G6_S31_04','L4','G6_P31','Add two negatives on line','Сложение двух отрицательных на прямой','Движение влево дважды',4,'apply',6,6,
 'Найдите -2 + (-4)','Движение влево дважды','Medium (Level B)',NULL);

-- ─── П.32: Сложение отрицательных чисел (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S32_01','L4','G6_P32','Add negatives rule','Сложение отрицательных по правилу','Применение правила (-a)+(-b)=-(a+b)',1,'apply',6,6,
 '-5 + (-3)','Применение правила (-a)+(-b)=-(a+b)','Low (Level A)','(−a) + (−b) = −(a + b)'),
('G6_S32_02','L4','G6_P32','Add larger negatives','Сложение больших отрицательных','Аккуратность вычисления',2,'apply',6,6,
 '-12 + (-8)','Аккуратность вычисления','Medium (Level B)',NULL),
('G6_S32_03','L4','G6_P32','Explain negative sum','Объяснение знака суммы','Анализ модулей',3,'analyze',6,6,
 'Объясните, почему результат отрицательный','Анализ модулей','Medium (Level B)','a + (−a) = 0');

-- ─── П.33: Сложение чисел с разными знаками (4 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S33_01','L4','G6_P33','Add different signs positive result','Сложение разных знаков с положительным результатом','Вычитание модулей',1,'apply',6,6,
 '7 + (-4)','Вычитание модулей','Medium (Level B)',NULL),
('G6_S33_02','L4','G6_P33','Add different signs negative result','Сложение разных знаков с отрицательным результатом','Определение знака результата',2,'apply',6,6,
 '5 + (-9)','Определение знака результата','Medium (Level B)',NULL),
('G6_S33_03','L4','G6_P33','Add opposites to zero','Сложение противоположных до нуля','Понимание нуля как результата',3,'apply',6,6,
 '-6 + 6','Понимание нуля как результата','Low (Level A)',NULL),
('G6_S33_04','L4','G6_P33','Add multiple mixed signs','Поэтапное сложение нескольких чисел','Поэтапное сложение',4,'apply',6,6,
 '-8 + 3 + (-2)','Поэтапное сложение','High (Level C)',NULL);

-- ─── П.34: Вычитание (4 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S34_01','L4','G6_P34','Subtract negative','Вычитание отрицательного числа','Переход к сложению a-b=a+(-b)',1,'apply',6,6,
 '5 - (-3)','Переход к сложению a-b=a+(-b)','Low (Level A)','a − b = a + (−b)'),
('G6_S34_02','L4','G6_P34','Subtract larger from smaller','Вычитание большего из меньшего','Применение правила',2,'apply',6,6,
 '4 - 7','Применение правила','Medium (Level B)',NULL),
('G6_S34_03','L4','G6_P34','Double negation subtraction','Двойное отрицание при вычитании','Двойное отрицание',3,'apply',6,6,
 '-6 - (-2)','Двойное отрицание','Medium (Level B)',NULL),
('G6_S34_04','L4','G6_P34','Subtract with brackets','Вычитание с раскрытием скобок','Раскрытие скобок и преобразование',4,'apply',6,6,
 '-3 - (5 - 8)','Раскрытие скобок и преобразование','High (Level C)',NULL);

-- ─── П.35: Умножение (4 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S35_01','L4','G6_P35','Multiply positives','Умножение положительных чисел','Базовое умножение',1,'apply',6,6,
 '4 × 6','Базовое умножение','Low (Level A)',NULL),
('G6_S35_02','L4','G6_P35','Multiply two negatives','Умножение двух отрицательных','Правило знаков: минус×минус=плюс',2,'apply',6,6,
 '(−5) × (−3)','Правило знаков: минус×минус=плюс','Low (Level A)','(−a) × (−b) = a × b'),
('G6_S35_03','L4','G6_P35','Multiply positive by negative','Умножение положительного на отрицательное','Определение знака результата',3,'apply',6,6,
 '7 × (−4)','Определение знака результата','Medium (Level B)','a × (−b) = −(a × b)'),
('G6_S35_04','L4','G6_P35','Multiply three signed numbers','Умножение трёх знаковых чисел','Последовательное применение правила знаков',4,'apply',6,6,
 '(−2) × 3 × (−4)','Последовательное применение правила знаков','High (Level C)',NULL);

-- ─── П.36: Деление (4 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S36_01','L4','G6_P36','Divide two negatives','Деление двух отрицательных','Правило знаков',1,'apply',6,6,
 '(−12) : (−3)','Правило знаков','Low (Level A)',NULL),
('G6_S36_02','L4','G6_P36','Divide positive by negative','Деление положительного на отрицательное','Определение знака результата',2,'apply',6,6,
 '15 : (−5)','Определение знака результата','Medium (Level B)',NULL),
('G6_S36_03','L4','G6_P36','Verify division result','Проверка результата деления','Обратная операция',3,'apply',6,6,
 'Проверьте результат (−18) : 6','Обратная операция','Medium (Level B)',NULL),
('G6_S36_04','L4','G6_P36','Chain division','Последовательное деление','Порядок действий',4,'apply',6,6,
 '(−24) : (−3) : 2','Порядок действий','High (Level C)',NULL);

-- ─── П.37: Рациональные числа (4 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S37_01','L4','G6_P37','Identify rational number','Определение рационального числа','Запись числа как −3/1',1,'recall',6,6,
 'Является ли −3 рациональным','Запись числа как −3/1','Low (Level A)',NULL),
('G6_S37_02','L4','G6_P37','Represent integer as fraction','Представление целого в виде дроби','Запись 5/1',2,'apply',6,6,
 'Представьте 5 в виде дроби','Запись 5/1','Low (Level A)',NULL),
('G6_S37_03','L4','G6_P37','Zero as rational','Ноль как рациональное число','Запись 0/1',3,'apply',6,6,
 'Является ли 0 рациональным','Запись 0/1','Medium (Level B)',NULL),
('G6_S37_04','L4','G6_P37','Add fraction and integer','Сложение дроби и целого числа','Представление 2 как 2/1',4,'apply',6,6,
 '−3/4 + 2','Представление 2 как 2/1','High (Level C)',NULL);

-- ─── П.38: Свойства действий с рациональными числами (4 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S38_01','L4','G6_P38','Commutative property','Переместительное свойство','Перестановка слагаемых',1,'apply',6,6,
 '−3 + 5 = 5 + (−3)','Перестановка слагаемых','Low (Level A)','a + b = b + a (переместительное)'),
('G6_S38_02','L4','G6_P38','Associative property','Сочетательное свойство','Группировка слагаемых',2,'apply',6,6,
 '(−2 + 4) + 6','Группировка слагаемых','Medium (Level B)','(a + b) + c = a + (b + c) (сочетательное)'),
('G6_S38_03','L4','G6_P38','Distributive property signed','Распределительное свойство со знаками','Раскрытие скобок',3,'apply',6,6,
 '−2(3 − 5)','Раскрытие скобок','Medium (Level B)','a(b + c) = ab + ac (распределительное)'),
('G6_S38_04','L4','G6_P38','Order of operations signed','Порядок действий со знаками','Порядок действий',4,'apply',6,6,
 '−3 + 2 × (4 − 7)','Порядок действий','High (Level C)',NULL);

-- ─── П.39: Раскрытие скобок (2 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S39_01','L4','G6_P39','Expand brackets positive','Раскрытие скобок с положительным множителем','Применение формулы a(b+c)=ab+ac',1,'apply',6,6,
 '3(x + 4)','Применение формулы a(b+c)=ab+ac','Medium (Level B)','a(b + c) = ab + ac'),
('G6_S39_02','L4','G6_P39','Expand brackets negative','Раскрытие скобок с отрицательным множителем','Правильная работа со знаком',2,'apply',6,6,
 '−2(x − 5)','Правильная работа со знаком','Medium (Level B)','−a(b + c) = −ab − ac');

-- ─── П.40: Коэффициент (2 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S40_01','L4','G6_P40','Find coefficient positive','Нахождение коэффициента','Выделение числа',1,'recall',6,6,
 'Найдите коэффициент в 7x','Выделение числа','Low (Level A)',NULL),
('G6_S40_02','L4','G6_P40','Find coefficient negative','Нахождение коэффициента с учётом знака','Учет знака',2,'apply',6,6,
 'Найдите коэффициент в −5a','Учет знака','Medium (Level B)',NULL);

-- ─── П.41: Подобные слагаемые (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S41_01','L4','G6_P41','Add like terms','Сложение подобных слагаемых','Сложение коэффициентов',1,'apply',6,6,
 '4x + 2x','Сложение коэффициентов','Low (Level A)',NULL),
('G6_S41_02','L4','G6_P41','Subtract like terms','Вычитание подобных слагаемых','Вычитание коэффициентов',2,'apply',6,6,
 '7a - 3a','Вычитание коэффициентов','Medium (Level B)',NULL),
('G6_S41_03','L4','G6_P41','Simplify with constants','Упрощение с константами','Разделение постоянных и переменных',3,'apply',6,6,
 '3x + 2 − x','Разделение постоянных и переменных','Medium (Level B)',NULL);

-- ─── П.42: Решение уравнений (4 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S42_01','L4','G6_P42','Solve simple equation','Решение простого уравнения','Вычитание',1,'apply',6,6,
 'x + 5 = 9','Вычитание','Low (Level A)',NULL),
('G6_S42_02','L4','G6_P42','Solve equation with transfer','Решение уравнения с переносом','Перенос слагаемого',2,'apply',6,6,
 'x − 4 = −2','Перенос слагаемого','Medium (Level B)',NULL),
('G6_S42_03','L4','G6_P42','Solve equation with division','Решение уравнения делением','Деление обеих частей',3,'apply',6,6,
 '3x = 12','Деление обеих частей','Medium (Level B)',NULL),
('G6_S42_04','L4','G6_P42','Solve equation with brackets','Решение уравнения со скобками','Раскрытие скобок и решение',4,'apply',6,6,
 '2(x − 3) = 8','Раскрытие скобок и решение','High (Level C)',NULL);

-- ─── П.43: Перпендикулярные прямые (4 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S43_01','L4','G6_P43','Perpendicular angle','Угол перпендикулярных прямых','Знание 90°',1,'recall',6,6,
 'Под каким углом пересекаются перпендикулярные прямые','Знание 90°','Low (Level A)',NULL),
('G6_S43_02','L4','G6_P43','Identify perpendicular lines','Определение перпендикулярности','Работа с инструментом',2,'apply',6,6,
 'Определите, перпендикулярны ли прямые','Работа с инструментом','Medium (Level B)',NULL),
('G6_S43_03','L4','G6_P43','Construct perpendicular','Построение перпендикуляра','Аккуратное построение',3,'apply',6,6,
 'Постройте прямую, перпендикулярную данной','Аккуратное построение','Medium (Level B)',NULL),
('G6_S43_04','L4','G6_P43','Perpendicular to axis','Перпендикуляр к оси','Понимание системы координат',4,'analyze',6,6,
 'Сколько прямых перпендикулярны оси Ox','Понимание системы координат','High (Level C)',NULL);

-- ─── П.44: Параллельные прямые (4 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S44_01','L4','G6_P44','Parallel lines definition','Определение параллельных прямых','Знание определения',1,'recall',6,6,
 'Могут ли параллельные прямые пересекаться','Знание определения','Low (Level A)',NULL),
('G6_S44_02','L4','G6_P44','Construct parallel line','Построение параллельной прямой','Работа с линейкой и угольником',2,'apply',6,6,
 'Постройте прямую, параллельную данной','Работа с линейкой и угольником','Medium (Level B)',NULL),
('G6_S44_03','L4','G6_P44','Axes parallel check','Проверка параллельности осей','Понимание взаимного расположения',3,'apply',6,6,
 'Ось Ox и Oy являются ли параллельными','Понимание взаимного расположения','Medium (Level B)',NULL),
('G6_S44_04','L4','G6_P44','Parallel sides of rectangle','Параллельные стороны прямоугольника','Анализ геометрической фигуры',4,'analyze',6,6,
 'Найдите пары параллельных сторон прямоугольника','Анализ геометрической фигуры','High (Level C)',NULL);

-- ─── П.45: Координатная плоскость (4 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S45_01','L4','G6_P45','Name point coordinates','Название координат точки','Правильный порядок записи',1,'apply',6,6,
 'Назовите координаты точки (3; -2)','Правильный порядок записи','Low (Level A)',NULL),
('G6_S45_02','L4','G6_P45','Plot point on plane','Построение точки на плоскости','Движение по оси x, затем по оси y',2,'apply',6,6,
 'Постройте точку (-4; 1)','Движение по оси x, затем по оси y','Medium (Level B)',NULL),
('G6_S45_03','L4','G6_P45','Determine quadrant','Определение четверти','Анализ знаков координат',3,'analyze',6,6,
 'В какой четверти находится точка (2; -5)','Анализ знаков координат','Medium (Level B)',NULL),
('G6_S45_04','L4','G6_P45','Distance to axis','Расстояние до оси','Использование модуля |y|',4,'apply',6,6,
 'Найдите расстояние точки (3; -4) до оси Ox','Использование модуля |y|','High (Level C)','Расстояние до оси Ox = |y|, до Oy = |x|');

-- ─── П.46: Столбчатые диаграммы (4 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S46_01','L4','G6_P46','Read bar chart','Чтение столбчатой диаграммы','Анализ столбцов',1,'apply',6,6,
 'Определите наибольшее значение по диаграмме','Анализ столбцов','Low (Level A)',NULL),
('G6_S46_02','L4','G6_P46','Build bar chart','Построение столбчатой диаграммы','Выбор масштаба',2,'apply',6,6,
 'Постройте диаграмму по данным','Выбор масштаба','Medium (Level B)',NULL),
('G6_S46_03','L4','G6_P46','Compare bar chart values','Сравнение значений по диаграмме','Вычисление разницы',3,'apply',6,6,
 'На сколько одно значение больше другого','Вычисление разницы','Medium (Level B)',NULL),
('G6_S46_04','L4','G6_P46','Interpret bar chart','Интерпретация диаграммы','Интерпретация информации',4,'evaluate',6,6,
 'Сделайте вывод по диаграмме','Интерпретация информации','High (Level C)',NULL);

-- ─── П.47: Графики (4 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G6_S47_01','L4','G6_P47','Read value from graph','Определение значения по графику','Работа с координатами',1,'apply',6,6,
 'Определите значение y при x = 2','Работа с координатами','Medium (Level B)',NULL),
('G6_S47_02','L4','G6_P47','Build value table','Составление таблицы значений','Вычисление значений',2,'apply',6,6,
 'Постройте таблицу для y = 2x','Вычисление значений','Medium (Level B)',NULL),
('G6_S47_03','L4','G6_P47','Plot graph','Построение графика','Нанесение точек и соединение',3,'apply',6,6,
 'Постройте график y = x + 1','Нанесение точек и соединение','High (Level C)',NULL),
('G6_S47_04','L4','G6_P47','Analyze graph behavior','Анализ поведения графика','Анализ направления графика',4,'analyze',6,6,
 'Определите, возрастает ли функция','Анализ направления графика','High (Level C)',NULL);

-- ============================================================================
-- Контрольный подсчёт
-- ============================================================================
SELECT level, COUNT(*) AS cnt
FROM knowledge_hierarchy
WHERE id LIKE 'G6_%'
GROUP BY level
ORDER BY level;
-- Ожидается: L1=2, L2=9, L3=47, L4=159  =>  Итого: 217
