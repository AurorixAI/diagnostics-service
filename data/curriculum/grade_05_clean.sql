-- ============================================================================
-- ALGO V1 — СКЕЛЕТ 5 КЛАСС (чистый методический файл)
-- Источник: Sardor Bozorov, PDF программа 5 класса
-- 2 раздела, 10 тем, 47 пунктов, 127 атомарных навыков
-- ============================================================================
-- ФОРМАТ: Только поля методиста. ИИ-поля (importance, typical_time_seconds,
-- irt_*, difficulty_score, weight, criticality) заполняются пайплайном.
-- Prerequisites — будут сгенерированы AI-пайплайном
-- ============================================================================

-- Очистка
DELETE FROM tasks_master WHERE skill_id LIKE 'G5_%';
DELETE FROM knowledge_hierarchy WHERE id LIKE 'G5_%';

-- ============================================================================
-- L1: РАЗДЕЛЫ (2)
-- ============================================================================
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, class_level_start, class_level_end, sequence_order)
VALUES
    ('G5_NAT',  'L1', NULL, 'Natural Numbers',   'Натуральные числа', 5, 5, 1),
    ('G5_FRAC', 'L1', NULL, 'Fractional Numbers', 'Дробные числа',    5, 5, 2);

-- ============================================================================
-- L2: ТЕМЫ (10)
-- ============================================================================
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, class_level_start, class_level_end, sequence_order)
VALUES
    ('G5_T01', 'L2', 'G5_NAT',  'Natural Numbers and Scales',   'Натуральные числа и шкалы',                    5, 5,  1),
    ('G5_T02', 'L2', 'G5_NAT',  'Addition and Subtraction',     'Сложение и вычитание натуральных чисел',       5, 5,  2),
    ('G5_T03', 'L2', 'G5_NAT',  'Multiplication and Division',  'Умножение и деление натуральных чисел',        5, 5,  3),
    ('G5_T04', 'L2', 'G5_NAT',  'Geometric Shapes',             'Геометрические фигуры',                        5, 5,  4),
    ('G5_T05', 'L2', 'G5_NAT',  'Areas and Volumes',            'Площади и объёмы',                             5, 5,  5),
    ('G5_T06', 'L2', 'G5_FRAC', 'Common Fractions',             'Обыкновенные дроби',                           5, 5,  6),
    ('G5_T07', 'L2', 'G5_FRAC', 'Decimal Fractions Add/Sub',    'Десятичные дроби. Сложение и вычитание',        5, 5,  7),
    ('G5_T08', 'L2', 'G5_FRAC', 'Decimal Fractions Mul/Div',    'Умножение и деление десятичных дробей',         5, 5,  8),
    ('G5_T09', 'L2', 'G5_FRAC', 'Data Analysis',                'Анализ данных',                                5, 5,  9),
    ('G5_T10', 'L2', 'G5_FRAC', 'Word Problems',                'Текстовые задачи',                             5, 5, 10);

-- ============================================================================
-- L3: ПУНКТЫ (47)
-- ============================================================================
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, class_level_start, class_level_end, sequence_order)
VALUES
    -- Тема 1
    ('G5_P01', 'L3', 'G5_T01', 'Natural Numbers',              'Натуральные числа',                              5, 5,  1),
    ('G5_P02', 'L3', 'G5_T01', 'Segment Ray Line',             'Отрезок, луч, прямая',                           5, 5,  2),
    ('G5_P03', 'L3', 'G5_T01', 'Scales and Number Line',       'Шкалы и числовая ось',                           5, 5,  3),
    ('G5_P04', 'L3', 'G5_T01', 'Comparing Natural Numbers',    'Сравнение натуральных чисел',                    5, 5,  4),
    ('G5_P05', 'L3', 'G5_T01', 'Rounding Natural Numbers',     'Округление натуральных чисел',                   5, 5,  5),
    -- Тема 2
    ('G5_P06', 'L3', 'G5_T02', 'Add Sub Natural Numbers',      'Сложение и вычитание натуральных чисел',         5, 5,  6),
    ('G5_P07', 'L3', 'G5_T02', 'Numeric Algebraic Expressions','Числовые и буквенные выражения',                 5, 5,  7),
    ('G5_P08', 'L3', 'G5_T02', 'Equations',                    'Уравнения',                                      5, 5,  8),
    -- Тема 3
    ('G5_P09', 'L3', 'G5_T03', 'Multiplication',               'Умножение натуральных чисел',                    5, 5,  9),
    ('G5_P10', 'L3', 'G5_T03', 'Division',                     'Деление натуральных чисел',                      5, 5, 10),
    ('G5_P11', 'L3', 'G5_T03', 'Division with Remainder',      'Деление с остатком',                             5, 5, 11),
    ('G5_P12', 'L3', 'G5_T03', 'Simplifying Expressions',      'Упрощение выражений',                            5, 5, 12),
    ('G5_P13', 'L3', 'G5_T03', 'Order of Operations',          'Порядок выполнения действий',                    5, 5, 13),
    ('G5_P14', 'L3', 'G5_T03', 'Square and Cube',              'Квадрат и куб числа',                            5, 5, 14),
    ('G5_P15', 'L3', 'G5_T03', 'GCD and LCM',                  'НОК и НОД',                                     5, 5, 15),
    -- Тема 4
    ('G5_P16', 'L3', 'G5_T04', 'Angles',                       'Углы',                                           5, 5, 16),
    ('G5_P17', 'L3', 'G5_T04', 'Parallel Perpendicular',       'Параллельные и перпендикулярные прямые',          5, 5, 17),
    ('G5_P18', 'L3', 'G5_T04', 'Polyline and Length',          'Ломаная и её длина',                              5, 5, 18),
    ('G5_P19', 'L3', 'G5_T04', 'Polygon Perimeter',            'Периметр многоугольника',                        5, 5, 19),
    -- Тема 5
    ('G5_P20', 'L3', 'G5_T05', 'Rectangle Area',               'Площадь прямоугольника',                         5, 5, 20),
    ('G5_P21', 'L3', 'G5_T05', 'Composite Area',               'Площадь составных фигур',                        5, 5, 21),
    ('G5_P22', 'L3', 'G5_T05', 'Area Units',                   'Единицы измерения площади',                      5, 5, 22),
    ('G5_P23', 'L3', 'G5_T05', 'Parallelepiped and Cube',      'Прямоугольный параллелепипед и куб',             5, 5, 23),
    ('G5_P24', 'L3', 'G5_T05', 'Volume',                       'Объём куба и прямоугольного параллелепипеда',    5, 5, 24),
    -- Тема 6
    ('G5_P25', 'L3', 'G5_T06', 'Parts and Fractions',          'Доли и обыкновенные дроби',                      5, 5, 25),
    ('G5_P26', 'L3', 'G5_T06', 'Comparing Fractions',          'Сравнение дробей',                               5, 5, 26),
    ('G5_P27', 'L3', 'G5_T06', 'Proper Improper Fractions',    'Правильные и неправильные дроби',                5, 5, 27),
    ('G5_P28', 'L3', 'G5_T06', 'Add Sub Fractions',            'Сложение и вычитание дробей',                    5, 5, 28),
    ('G5_P29', 'L3', 'G5_T06', 'Division and Fractions',       'Деление и дроби',                                5, 5, 29),
    ('G5_P30', 'L3', 'G5_T06', 'Mixed Numbers',                'Смешанные числа',                                5, 5, 30),
    ('G5_P31', 'L3', 'G5_T06', 'Add Sub Mixed Numbers',        'Сложение и вычитание смешанных чисел',           5, 5, 31),
    -- Тема 7
    ('G5_P32', 'L3', 'G5_T07', 'Decimal Fractions',            'Десятичные дроби',                               5, 5, 32),
    ('G5_P33', 'L3', 'G5_T07', 'Comparing Decimals',           'Сравнение десятичных дробей',                    5, 5, 33),
    ('G5_P34', 'L3', 'G5_T07', 'Add Sub Decimals',             'Сложение и вычитание десятичных дробей',         5, 5, 34),
    ('G5_P35', 'L3', 'G5_T07', 'Rounding Decimals',            'Приближённое значение и округление десятичных',  5, 5, 35),
    -- Тема 8
    ('G5_P36', 'L3', 'G5_T08', 'Mul Decimal by Natural',       'Умножение десятичной дроби на натуральное число',5, 5, 36),
    ('G5_P37', 'L3', 'G5_T08', 'Div Decimal by Natural',       'Деление десятичных дробей на натуральные числа', 5, 5, 37),
    ('G5_P38', 'L3', 'G5_T08', 'Multiply Decimals',            'Умножение десятичных дробей',                    5, 5, 38),
    ('G5_P39', 'L3', 'G5_T08', 'Divide Decimals',              'Деление десятичных дробей',                      5, 5, 39),
    -- Тема 9
    ('G5_P40', 'L3', 'G5_T09', 'Percentages',                  'Проценты',                                       5, 5, 40),
    ('G5_P41', 'L3', 'G5_T09', 'Arithmetic Mean',              'Среднее арифметическое ряда данных',             5, 5, 41),
    ('G5_P42', 'L3', 'G5_T09', 'Data Series',                  'Ряды данных и их анализ',                        5, 5, 42),
    -- Тема 10
    ('G5_P43', 'L3', 'G5_T10', 'Fraction Problems',            'Задачи на дроби',                                5, 5, 43),
    ('G5_P44', 'L3', 'G5_T10', 'Motion Problems',              'Задачи на движение',                             5, 5, 44),
    ('G5_P45', 'L3', 'G5_T10', 'Two Body Motion',              'Задачи на движение двух тел',                    5, 5, 45),
    ('G5_P46', 'L3', 'G5_T10', 'Economic Problems',            'Задачи с экономическим содержанием',             5, 5, 46),
    ('G5_P47', 'L3', 'G5_T10', 'Work Problems',                'Задачи на выполненную работу',                   5, 5, 47);

-- ============================================================================
-- L4: АТОМАРНЫЕ НАВЫКИ (126)
-- Каждый навык содержит: example_task, assessed_ability, difficulty_level, formula из PDF
-- ============================================================================

-- ─── П.1: Натуральные числа (4 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S01_01','L4','G5_P01','Identify natural numbers','Определение натуральных чисел','Какие числа являются натуральными',1,'recall',5,5,
 'Какие числа из списка 0, 1, 3, 7, −2 являются натуральными?','Понимание определения','Low (Level A)',NULL),
('G5_S01_02','L4','G5_P01','Read and write naturals','Запись и чтение натуральных чисел','Чтение и запись чисел словами',2,'apply',5,5,
 'Прочитайте число 4 507 и запишите его словами','Чтение и запись чисел','Low (Level A)',NULL),
('G5_S01_03','L4','G5_P01','Place value decomposition','Разрядный состав числа','Разложение по разрядам',3,'apply',5,5,
 'Разложите число 3 482 по разрядам','Анализ структуры числа','Low (Level A-B)',NULL),
('G5_S01_04','L4','G5_P01','Write number from words','Запись числа цифрами','Запись числа из словесного описания',4,'apply',5,5,
 'Запишите цифрами число: два миллиона шестьсот сорок пять тысяч восемьсот пятьдесят девять','Восприятие прописного варианта числа','Low (Level A-B)',NULL);

-- ─── П.2: Отрезок, луч, прямая (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S02_01','L4','G5_P02','Distinguish geometric objects','Различие геометрических объектов','Распознавание прямая/луч/отрезок',1,'recall',5,5,
 'Укажите, где изображены прямая, луч и отрезок','Распознавание понятий','Low (Level A)',NULL),
('G5_S02_02','L4','G5_P02','Segment notation','Обозначение отрезка','Корректная запись обозначений',2,'recall',5,5,
 'Как обозначается отрезок с концами A и B?','Корректная запись','Low (Level A)',NULL),
('G5_S02_03','L4','G5_P02','Compare lengths','Сравнение по длине','Сравнение длин отрезков',3,'apply',5,5,
 'Какой из отрезков длиннее?','Сравнение геометрических величин','Low (Level A-B)',NULL);

-- ─── П.3: Шкалы и числовая ось (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S03_01','L4','G5_P03','Understand scale','Понимание шкалы','Что показывает одно деление',1,'recall',5,5,
 'Что показывает одно деление шкалы?','Восприятие шкалы','Low (Level A)',NULL),
('G5_S03_02','L4','G5_P03','Plot number on axis','Нахождение числа на оси','Отметка числа на числовой оси',2,'apply',5,5,
 'Отметьте число 6 на числовой оси','Работа с числовой осью','Low (Level A)',NULL),
('G5_S03_03','L4','G5_P03','Read coordinate of point','Определение координаты точки','Чтение графической информации',3,'apply',5,5,
 'Найдите координату отмеченной точки','Чтение графической информации','Low (Level A-B)',NULL);

-- ─── П.4: Сравнение натуральных чисел (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S04_01','L4','G5_P04','Compare by notation','Сравнение по записи','Сравнение чисел по разрядам',1,'apply',5,5,
 'Какое число больше: 4 305 или 4 350?','Сравнение чисел','Low (Level A)',NULL),
('G5_S04_02','L4','G5_P04','Use comparison signs','Использование знаков <, >, =','Символьная запись сравнения',2,'apply',5,5,
 'Поставьте нужный знак: 678 _ 689','Символьная запись сравнения','Low (Level A)',NULL),
('G5_S04_03','L4','G5_P04','Compare multi-digit','Сравнение многозначных чисел','Анализ разрядов',3,'apply',5,5,
 'Сравните 120 345 и 119 999','Анализ разрядов','Low (Level A-B)',NULL);

-- ─── П.5: Округление натуральных чисел (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S05_01','L4','G5_P05','Round to tens','Округление до десятков','Применение правила округления',1,'apply',5,5,
 'Округлите 347 до десятков','Применение правила округления','Low (Level A)',NULL),
('G5_S05_02','L4','G5_P05','Round to hundreds','Округление до сотен','Анализ соседних разрядов',2,'apply',5,5,
 'Округлите 6 482 до сотен','Анализ соседних разрядов','Low (Level A-B)',NULL),
('G5_S05_03','L4','G5_P05','Identify rounding digit','Выбор разряда округления','Интерпретация результата',3,'analyze',5,5,
 'До какого разряда округлено число 4 000?','Интерпретация результата','Medium (Level B)',NULL);

-- ─── П.6: Сложение и вычитание натуральных чисел (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S06_01','L4','G5_P06','Addition without carry','Сложение без перехода через разряд','Базовые вычисления',1,'apply',5,5,
 '234 + 145','Базовые вычисления','Low (Level A)',NULL),
('G5_S06_02','L4','G5_P06','Addition with carry','Сложение с переходом','Работа с переносом',2,'apply',5,5,
 '587 + 368','Работа с переносом','Low (Level A-B)',NULL),
('G5_S06_03','L4','G5_P06','Subtraction with borrowing','Вычитание с занятием','Корректное заимствование',3,'apply',5,5,
 '702 - 468','Корректное заимствование','Medium (Level B)',NULL);

-- ─── П.7: Числовые и буквенные выражения (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S07_01','L4','G5_P07','Identify expression type','Определение выражения','Классификация выражений',1,'recall',5,5,
 'Что является числовым выражением?','Классификация','Low (Level A)',NULL),
('G5_S07_02','L4','G5_P07','Substitute variable value','Подстановка значения буквы','Подстановка и вычисление',2,'apply',5,5,
 'Найдите значение 3a + 5 при a = 4','Подстановка','Low (Level A)',NULL),
('G5_S07_03','L4','G5_P07','Write algebraic expression','Запись буквенного выражения','Математическая запись',3,'apply',5,5,
 'Запишите сумму числа x и 7','Математическая запись','Low (Level A-B)',NULL);

-- ─── П.8: Уравнения (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S08_01','L4','G5_P08','Understand equation','Понимание уравнения','Терминология',1,'recall',5,5,
 'Что называется уравнением?','Терминология','Low (Level A)',NULL),
('G5_S08_02','L4','G5_P08','Solve simple equation','Решение простого уравнения','Поиск неизвестного',2,'apply',5,5,
 '4x : 8 + 9 = 12','Поиск неизвестного','Low (Level A)',NULL),
('G5_S08_03','L4','G5_P08','Check solution','Проверка решения','Проверка подстановкой',3,'apply',5,5,
 'Является ли 5 корнем уравнения x + 3 = 8?','Проверка подстановкой','Medium (Level B)',NULL);

-- ─── П.9: Умножение натуральных чисел (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S09_01','L4','G5_P09','Multiplication table','Табличное умножение','Знание таблицы умножения',1,'recall',5,5,
 '7 × 8','Знание таблицы','Low (Level A)',NULL),
('G5_S09_02','L4','G5_P09','Multi-digit multiplication','Умножение многозначных чисел','Алгоритм умножения',2,'apply',5,5,
 '34 × 6','Алгоритм умножения','Low (Level A-B)',NULL),
('G5_S09_03','L4','G5_P09','Multiplication properties','Свойства умножения','Применение свойств',3,'apply',5,5,
 'Используйте переместительное свойство','Применение свойств','Medium (Level B)',NULL);

-- ─── П.10: Деление натуральных чисел (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S10_01','L4','G5_P10','Understanding division','Понимание деления','Смысл операции',1,'recall',5,5,
 'Что означает 612 : 3?','Смысл операции','Low (Level A)',NULL),
('G5_S10_02','L4','G5_P10','Division without remainder','Деление без остатка','Вычисления',2,'apply',5,5,
 '348 : 6','Вычисления','Low (Level A)',NULL),
('G5_S10_03','L4','G5_P10','Check division','Проверка деления умножением','Обратная операция',3,'apply',5,5,
 'Проверьте 56 : 7','Обратная операция','Medium (Level B)',NULL);

-- ─── П.11: Деление с остатком (2 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S11_01','L4','G5_P11','Determine remainder','Определение остатка','Понимание остатка',1,'apply',5,5,
 '17 : 5','Понимание остатка','Low (Level A)','a = b × c + d, где a — делимое, b — делитель, c — неполное частное, d — остаток'),
('G5_S11_02','L4','G5_P11','Write division with remainder','Запись результата','Корректная запись',2,'apply',5,5,
 'Запишите деление с остатком','Корректная запись','Low (Level A-B)',NULL);

-- ─── П.12: Упрощение выражений (2 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S12_01','L4','G5_P12','Combine like terms','Сложение подобных слагаемых','Работа с подобными',1,'apply',5,5,
 '3a + 5a = 8a','Работа с подобными','Low (Level A)',NULL),
('G5_S12_02','L4','G5_P12','Simplify expression','Упрощение выражения','Алгебраические преобразования',2,'apply',5,5,
 '2x + 4x - x','Алгебраические преобразования','Medium (Level B)',NULL);

-- ─── П.13: Порядок выполнения действий (2 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S13_01','L4','G5_P13','Understand priorities','Понимание приоритетов','Теория',1,'recall',5,5,
 'Что выполняется первым?','Теория','Low (Level A)',NULL),
('G5_S13_02','L4','G5_P13','Calculate with brackets','Вычисление со скобками','Следование алгоритму',2,'apply',5,5,
 '(8 + 4) × 3','Следование алгоритму','Low (Level A-B)',NULL);

-- ─── П.14: Квадрат и куб числа (2 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S14_01','L4','G5_P14','Square concept','Понятие квадрата','Понимание степени',1,'recall',5,5,
 'Что означает 5²?','Понимание степени','Low (Level A)','a² = a × a'),
('G5_S14_02','L4','G5_P14','Calculate square and cube','Вычисление квадрата и куба','Вычисления',2,'apply',5,5,
 'Найдите 4² и 3³','Вычисления','Low (Level A)','a² = a × a, a³ = a × a × a');

-- ─── П.15: НОК и НОД (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S15_01','L4','G5_P15','Find GCD','Нахождение НОД','Разложение на множители',1,'apply',5,5,
 'Найти НОД(24, 36)','Разложение на множители и поиск общих делителей','Low (Level A)',NULL),
('G5_S15_02','L4','G5_P15','Find LCM','Нахождение НОК','Нахождение кратных',2,'apply',5,5,
 'Найти НОК(12, 18)','Нахождение кратных чисел через простые множители','Medium (Level B)',NULL),
('G5_S15_03','L4','G5_P15','GCD LCM formula','Связь НОД и НОК','Формула НОК(a,b)·НОД(a,b)=a·b',3,'apply',5,5,
 'Проверьте формулу НОК(a,b)·НОД(a,b)=a·b','Применение формулы связи','Medium (Level B)','НОК(a,b) × НОД(a,b) = a × b');

-- ─── П.16: Углы (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S16_01','L4','G5_P16','Recognize angle','Распознавание угла','Геометрическое понимание',1,'recall',5,5,
 'Что называется углом?','Геометрическое понимание','Low (Level A)',NULL),
('G5_S16_02','L4','G5_P16','Angle types','Виды углов','Классификация',2,'recall',5,5,
 'Определите вид угла 90°','Классификация','Low (Level A)',NULL),
('G5_S16_03','L4','G5_P16','Measure angles','Измерение углов','Работа с инструментом',3,'apply',5,5,
 'Измерьте угол транспортиром','Работа с инструментом','Medium (Level B)',NULL);

-- ─── П.17: Параллельные и перпендикулярные прямые (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S17_01','L4','G5_P17','Recognize parallel','Распознавание параллельных прямых','Понимание параллельности',1,'recall',5,5,
 'Какие из изображённых прямых параллельны?','Понимание понятия параллельности','Low (Level A)',NULL),
('G5_S17_02','L4','G5_P17','Recognize perpendicular','Распознавание перпендикулярных прямых','Распознавание прямого угла',2,'recall',5,5,
 'Найдите пару перпендикулярных прямых','Распознавание прямого угла','Low (Level A)',NULL),
('G5_S17_03','L4','G5_P17','Line relation notation','Обозначение отношений между прямыми','Математическая запись',3,'apply',5,5,
 'Запишите: прямая a перпендикулярна прямой b','Математическая запись','Medium (Level B)',NULL);

-- ─── П.18: Ломаная и её длина (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S18_01','L4','G5_P18','Polyline concept','Понятие ломаной','Определение понятия',1,'recall',5,5,
 'Является ли данная фигура ломаной?','Определение понятия','Low (Level A)',NULL),
('G5_S18_02','L4','G5_P18','Calculate polyline length','Подсчёт длины ломаной','Сложение длин',2,'apply',5,5,
 'Найдите длину ломаной из отрезков 3 см, 5 см и 4 см','Сложение длин','Low (Level A)',NULL),
('G5_S18_03','L4','G5_P18','Work with scale','Работа с масштабом','Перевод длины',3,'apply',5,5,
 'Найдите длину ломаной по чертежу с масштабом','Перевод длины','Medium (Level B)',NULL);

-- ─── П.19: Периметр многоугольника (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S19_01','L4','G5_P19','Perimeter concept','Понимание периметра','Терминология',1,'recall',5,5,
 'Что называется периметром многоугольника?','Терминология','Low (Level A)',NULL),
('G5_S19_02','L4','G5_P19','Rectangle perimeter','Периметр прямоугольника','Применение формулы',2,'apply',5,5,
 'Найдите периметр прямоугольника со сторонами 5 см и 7 см','Применение формулы','Low (Level A)','P = 2(a + b)'),
('G5_S19_03','L4','G5_P19','Polygon perimeter','Периметр произвольного многоугольника','Сложение сторон',3,'apply',5,5,
 'Найдите периметр фигуры по чертежу','Сложение сторон','Medium (Level B)',NULL);

-- ─── П.20: Площадь прямоугольника (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S20_01','L4','G5_P20','Area concept','Понятие площади','Понимание смысла',1,'recall',5,5,
 'Что показывает площадь фигуры?','Понимание смысла','Low (Level A)',NULL),
('G5_S20_02','L4','G5_P20','Rectangle area formula','Формула площади прямоугольника','Применение формулы',2,'apply',5,5,
 'Найдите площадь прямоугольника 6 см × 4 см','Применение формулы','Low (Level A)','S = a × b'),
('G5_S20_03','L4','G5_P20','Inverse area problems','Обратные задачи','Логическое рассуждение',3,'analyze',5,5,
 'Найдите сторону прямоугольника по площади','Логическое рассуждение','Medium (Level B)',NULL);

-- ─── П.21: Площадь составных фигур (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S21_01','L4','G5_P21','Decompose shape','Разбиение фигуры','Анализ фигуры',1,'analyze',5,5,
 'На какие прямоугольники можно разбить фигуру?','Анализ фигуры','Low (Level A)',NULL),
('G5_S21_02','L4','G5_P21','Sum partial areas','Нахождение площади по частям','Сложение площадей',2,'apply',5,5,
 'Найдите площадь составной фигуры','Сложение площадей','Medium (Level B)',NULL),
('G5_S21_03','L4','G5_P21','Choose strategy','Выбор способа решения','Выбор стратегии',3,'evaluate',5,5,
 'Каким способом удобнее найти площадь?','Выбор стратегии','Medium-High (Level B-C)',NULL);

-- ─── П.22: Единицы измерения площади (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S22_01','L4','G5_P22','Know area units','Знание единиц площади','Знание терминов',1,'recall',5,5,
 'Назовите единицы площади','Знание терминов','Low (Level A)',NULL),
('G5_S22_02','L4','G5_P22','Convert area units','Перевод единиц','Перевод единиц',2,'apply',5,5,
 'Переведите 3 дм² в см²','Перевод единиц','Low (Level A-B)','1 дм² = 100 см², 1 м² = 10000 см²'),
('G5_S22_03','L4','G5_P22','Choose appropriate unit','Выбор корректной единицы','Практическое применение',3,'evaluate',5,5,
 'В каких единицах удобно измерять площадь комнаты?','Практическое применение','Medium (Level B)',NULL);

-- ─── П.23: Прямоугольный параллелепипед и куб (2 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S23_01','L4','G5_P23','Recognize 3D shapes','Распознавание тел','Пространственное мышление',1,'recall',5,5,
 'Какая фигура является кубом?','Пространственное мышление','Low (Level A)',NULL),
('G5_S23_02','L4','G5_P23','Count elements','Элементы тела','Анализ структуры',2,'recall',5,5,
 'Сколько рёбер у куба?','Анализ структуры','Low (Level A-B)',NULL);

-- ─── П.24: Объём куба и прямоугольного параллелепипеда (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S24_01','L4','G5_P24','Volume concept','Понятие объёма','Понимание физического смысла',1,'recall',5,5,
 'Что показывает объём тела?','Понимание физического смысла','Low (Level A)',NULL),
('G5_S24_02','L4','G5_P24','Parallelepiped volume','Формула объёма прямоугольного параллелепипеда','V=a×b×c',2,'apply',5,5,
 'Найдите объём тела со сторонами 4 см, 5 см и 6 см','Применение формулы','Low (Level A-B)','V = a × b × c'),
('G5_S24_03','L4','G5_P24','Cube volume','Объём куба','V=a³',3,'apply',5,5,
 'Найдите объём куба с ребром 7 см','Использование частного случая формулы','Medium (Level B)','V = a³');

-- ─── П.25: Доли и обыкновенные дроби (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S25_01','L4','G5_P25','Fraction concept','Понятие доли','Понимание дроби',1,'recall',5,5,
 'Что такое 1/4 фигуры?','Понимание дроби','Low (Level A)',NULL),
('G5_S25_02','L4','G5_P25','Write fraction','Запись дроби','Связь рисунка и записи',2,'apply',5,5,
 'Какая дробь закрашенной части?','Связь рисунка и записи','Low (Level A)',NULL),
('G5_S25_03','L4','G5_P25','Read fractions','Чтение дробей','Корректное чтение',3,'recall',5,5,
 'Прочитайте дробь 3/5','Корректное чтение','Low (Level A)',NULL);

-- ─── П.26: Сравнение дробей (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S26_01','L4','G5_P26','Compare same denominator','Сравнение с одинаковыми знаменателями','Анализ числителя',1,'apply',5,5,
 'Какая дробь больше: 3/7 или 5/7?','Анализ числителя','Low (Level A)',NULL),
('G5_S26_02','L4','G5_P26','Compare same numerator','Сравнение с одинаковыми числителями','Анализ знаменателя',2,'apply',5,5,
 'Сравните 3/4 и 3/8','Анализ знаменателя','Low (Level A-B)',NULL),
('G5_S26_03','L4','G5_P26','Compare with one','Сравнение с единицей','Аналитическое сравнение',3,'analyze',5,5,
 'Какая дробь больше 1?','Аналитическое сравнение','Medium (Level B)',NULL);

-- ─── П.27: Правильные и неправильные дроби (2 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S27_01','L4','G5_P27','Classify fractions','Распознавание дробей','Классификация',1,'recall',5,5,
 'Какие дроби являются правильными?','Классификация','Low (Level A)',NULL),
('G5_S27_02','L4','G5_P27','Compare numer and denom','Сравнение числителя и знаменателя','Анализ записи',2,'apply',5,5,
 'Является ли дробь 7/5 правильной?','Анализ записи','Low (Level A)',NULL);

-- ─── П.28: Сложение и вычитание дробей (4 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S28_01','L4','G5_P28','Add fractions same denom','Сложение дробей с одинаковыми знаменателями','Применение правила',1,'apply',5,5,
 '3/8 + 2/8','Применение правила','Low (Level A)',NULL),
('G5_S28_02','L4','G5_P28','Subtract fractions','Вычитание дробей','Работа с дробями',2,'apply',5,5,
 '5/6 − 1/6','Работа с дробями','Low (Level A-B)',NULL),
('G5_S28_03','L4','G5_P28','Check result','Проверка результата','Самоконтроль',3,'apply',5,5,
 'Верно ли вычислено выражение?','Самоконтроль','Medium (Level B)',NULL),
('G5_S28_04','L4','G5_P28','Add fractions diff denom','Сложение и вычитание дробей с разными знаменателями','Приведение к общему знаменателю',4,'apply',5,5,
 '3/5 + 1/14','Приведение к общему знаменателю','Medium (Level B)',NULL);

-- ─── П.29: Деление и дроби (2 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S29_01','L4','G5_P29','Fraction as division','Представление дроби как деления','Связь операций',1,'recall',5,5,
 'Что означает дробь 3/4?','Связь операций','Low (Level A)',NULL),
('G5_S29_02','L4','G5_P29','Write division as fraction','Запись деления в виде дроби','Преобразование',2,'apply',5,5,
 'Запишите 7 : 5 в виде дроби','Преобразование','Low (Level A)',NULL);

-- ─── П.30: Смешанные числа (2 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S30_01','L4','G5_P30','Mixed number concept','Понимание смешанного числа','Интерпретация записи',1,'recall',5,5,
 'Что означает 2 1/3?','Интерпретация записи','Low (Level A)',NULL),
('G5_S30_02','L4','G5_P30','Convert to improper','Перевод в неправильную дробь','Алгоритм преобразования',2,'apply',5,5,
 'Преобразуйте 3 2/5 в неправильную дробь','Алгоритм преобразования','Medium (Level B)',NULL);

-- ─── П.31: Сложение и вычитание смешанных чисел (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S31_01','L4','G5_P31','Add mixed no carry','Сложение без перехода','Работа с дробной частью',1,'apply',5,5,
 '1 2/5 + 2 1/5','Работа с дробной частью','Medium (Level B)',NULL),
('G5_S31_02','L4','G5_P31','Add sub mixed diff denom','Сложение и вычитание с разными знаменателями','Перенос единицы',2,'apply',5,5,
 '5 4/5 − 2 3/7','Перенос единицы','Medium-High (Level B-C)',NULL),
('G5_S31_03','L4','G5_P31','Add sub with carry','Сложение и вычитание с переходом через целое','Перенос единицы',3,'apply',5,5,
 '3 4/5 + 1 2/5','Перенос единицы','Medium-High (Level B-C)',NULL);

-- ─── П.32: Десятичные дроби (4 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S32_01','L4','G5_P32','Decimal concept','Понимание десятичной дроби','Понимание разрядов',1,'recall',5,5,
 'Что означает запись 2,35?','Понимание разрядов','Low (Level A)',NULL),
('G5_S32_02','L4','G5_P32','Read decimals','Чтение десятичных дробей','Корректное чтение',2,'recall',5,5,
 'Прочитайте дробь 0,407','Корректное чтение','Low (Level A)',NULL),
('G5_S32_03','L4','G5_P32','Write decimals','Запись десятичной дроби','Перевод слов в запись',3,'apply',5,5,
 'Запишите три целых и восемь сотых','Перевод слов в запись','Low (Level A-B)',NULL),
('G5_S32_04','L4','G5_P32','Decimal to fraction','Перевод десятичной дроби в обыкновенную/смешанную','Правильный перевод',4,'apply',5,5,
 '5,76 → 5 76/100','Правильный перевод','Low (Level A-B)',NULL);

-- ─── П.33: Сравнение десятичных дробей (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S33_01','L4','G5_P33','Compare integer parts','Сравнение целых частей','Анализ целой части',1,'apply',5,5,
 'Что больше: 3,5 или 4,1?','Анализ целой части','Low (Level A)',NULL),
('G5_S33_02','L4','G5_P33','Compare decimal parts','Сравнение дробной части','Поразрядное сравнение',2,'apply',5,5,
 'Сравните 2,35 и 2,305','Поразрядное сравнение','Low (Level A-B)',NULL),
('G5_S33_03','L4','G5_P33','Number line for decimals','Использование числовой оси','Геометрическое восприятие',3,'apply',5,5,
 'Какая дробь правее на оси?','Геометрическое восприятие','Medium (Level B)',NULL);

-- ─── П.34: Сложение и вычитание десятичных дробей (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S34_01','L4','G5_P34','Add decimals same digits','Сложение с одинаковым числом знаков','Базовый алгоритм',1,'apply',5,5,
 '3,4 + 2,5','Базовый алгоритм','Low (Level A)',NULL),
('G5_S34_02','L4','G5_P34','Add decimals diff digits','Сложение с разным числом знаков','Выравнивание разрядов',2,'apply',5,5,
 '4,27 + 1,8','Выравнивание разрядов','Medium (Level B)',NULL),
('G5_S34_03','L4','G5_P34','Subtract decimals','Вычитание десятичных дробей','Точность вычислений',3,'apply',5,5,
 '6,2 − 3,85','Точность вычислений','Medium (Level B)',NULL);

-- ─── П.35: Приближённое значение и округление десятичных дробей (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S35_01','L4','G5_P35','Round to tenths','Округление до десятых','Правила округления',1,'apply',5,5,
 'Округлите 3,46 до десятых','Правила округления','Low (Level A)',NULL),
('G5_S35_02','L4','G5_P35','Round to hundredths','Округление до сотых','Анализ следующего разряда',2,'apply',5,5,
 'Округлите 7,384 до сотых','Анализ следующего разряда','Low (Level A-B)',NULL),
('G5_S35_03','L4','G5_P35','Approximate calculations','Приближённые вычисления','Оценка результата',3,'apply',5,5,
 'Найдите приближённую сумму','Оценка результата','Medium (Level B)',NULL);

-- ─── П.36: Умножение десятичной дроби на натуральное число (2 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S36_01','L4','G5_P36','Multiply decimal basic','Умножение без переноса запятой','Базовое умножение',1,'apply',5,5,
 '0,4 × 3','Базовое умножение','Low (Level A)',NULL),
('G5_S36_02','L4','G5_P36','Multiply decimal carry','Перенос запятой','Алгоритм умножения',2,'apply',5,5,
 '2,35 × 4','Алгоритм умножения','Medium (Level B)',NULL);

-- ─── П.37: Деление десятичных дробей на натуральные числа (2 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S37_01','L4','G5_P37','Divide decimal exact','Деление нацело','Деление десятичной дроби',1,'apply',5,5,
 '4,8 : 6','Деление десятичной дроби','Low (Level A)',NULL),
('G5_S37_02','L4','G5_P37','Divide decimal continued','Деление с продолжением','Пошаговый алгоритм',2,'apply',5,5,
 '7,5 : 4','Пошаговый алгоритм','Medium (Level B)',NULL);

-- ─── П.38: Умножение десятичных дробей (2 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S38_01','L4','G5_P38','Multiply decimals','Умножение дробей без учёта запятой','Алгоритм умножения',1,'apply',5,5,
 'Выполните умножение 1,2 × 0,3','Алгоритм умножения','Medium (Level B)',NULL),
('G5_S38_02','L4','G5_P38','Place decimal point','Определение положения запятой','Контроль точности',2,'apply',5,5,
 'Где поставить запятую в результате?','Контроль точности','Medium-High (Level B-C)',NULL);

-- ─── П.39: Деление десятичных дробей (2 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S39_01','L4','G5_P39','Divide by 10 100 1000','Деление на 10, 100, 1000','Работа с разрядами',1,'apply',5,5,
 '3,45 : 10','Работа с разрядами','Low (Level A)',NULL),
('G5_S39_02','L4','G5_P39','Divide decimal by decimal','Деление дроби на дробь','Преобразование деления',2,'apply',5,5,
 '4,5 : 0,3','Преобразование деления','High (Level C)',NULL);

-- ─── П.40: Проценты (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S40_01','L4','G5_P40','Percent concept','Понимание процента','Связь с дробями',1,'recall',5,5,
 'Что означает 1%?','Связь с дробями','Low (Level A)','1% = 1/100'),
('G5_S40_02','L4','G5_P40','Find percent of number','Нахождение процента от числа','Практическое применение',2,'apply',5,5,
 'Найдите 20% от 50','Практическое применение','Medium (Level B)',NULL),
('G5_S40_03','L4','G5_P40','Find number by percent','Нахождение числа по проценту','Обратная задача',3,'analyze',5,5,
 '30% числа равны 15. Найдите число','Обратная задача','High (Level C)',NULL);

-- ─── П.41: Среднее арифметическое ряда данных (2 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S41_01','L4','G5_P41','Mean concept','Понимание среднего арифметического','Терминология',1,'recall',5,5,
 'Что называют средним арифметическим?','Терминология','Low (Level A)',NULL),
('G5_S41_02','L4','G5_P41','Calculate mean','Вычисление среднего','Применение формулы',2,'apply',5,5,
 'Найдите среднее чисел 4, 6 и 8','Применение формулы','Low (Level A-B)','Среднее = (a₁ + a₂ + ... + aₙ) / n');

-- ─── П.42: Ряды данных и их анализ (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S42_01','L4','G5_P42','Find range','Определение размаха','Анализ ряда',1,'apply',5,5,
 'Найдите размах данных','Анализ ряда','Low (Level A)',NULL),
('G5_S42_02','L4','G5_P42','Find median','Нахождение медианы','Упорядочивание данных',2,'apply',5,5,
 'Найдите медиану ряда','Упорядочивание данных','Medium (Level B)',NULL),
('G5_S42_03','L4','G5_P42','Find mode','Определение моды','Статистический анализ',3,'apply',5,5,
 'Какое значение встречается чаще всего?','Статистический анализ','Medium (Level B)',NULL);

-- ─── П.43: Задачи на дроби (3 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S43_01','L4','G5_P43','Find fraction of quantity','Нахождение дроби от величины','Применение дроби',1,'apply',5,5,
 'Найдите 2/5 от 30','Применение дроби','Medium (Level B)',NULL),
('G5_S43_02','L4','G5_P43','Find quantity by fraction','Нахождение величины по дроби','Обратное рассуждение',2,'analyze',5,5,
 '3/4 пути — 12 км. Найдите весь путь','Обратное рассуждение','High (Level C)',NULL),
('G5_S43_03','L4','G5_P43','Find number by fraction','Нахождение числа по дроби','Обратное действие',3,'analyze',5,5,
 '4/7 числа равны 28. Найдите число','Обратное действие','High (Level C)',NULL);

-- ─── П.44: Задачи на движение (2 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S44_01','L4','G5_P44','Speed time distance','Понимание связи путь-время-скорость','S=V×t',1,'recall',5,5,
 'Что показывает скорость?','Осмысление величин','Low (Level A)','S = v × t'),
('G5_S44_02','L4','G5_P44','Find distance','Нахождение пути','Применение формулы',2,'apply',5,5,
 'Найдите путь при v = 6 км/ч, t = 4 ч','Применение формулы','Medium (Level B)','S = v × t, v = S/t, t = S/v');

-- ─── П.45: Задачи на движение двух тел (2 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S45_01','L4','G5_P45','Motion towards','Движение навстречу','Работа с суммой скоростей',1,'analyze',5,5,
 'Найдите время встречи','Работа с суммой скоростей','High (Level C)',NULL),
('G5_S45_02','L4','G5_P45','Motion same direction','Движение в одном направлении','Анализ относительного движения',2,'analyze',5,5,
 'Найдите расстояние между телами','Анализ относительного движения','High (Level C)',NULL);

-- ─── П.46: Задачи с экономическим содержанием (2 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S46_01','L4','G5_P46','Price quantity cost','Цена, количество, стоимость','Экономическая модель',1,'apply',5,5,
 'Найдите стоимость покупки','Экономическая модель','Medium (Level B)',NULL),
('G5_S46_02','L4','G5_P46','Discounts and markups','Скидки и наценки','Работа с процентами',2,'analyze',5,5,
 'Цена снижена на 10%','Работа с процентами','High (Level C)',NULL);

-- ─── П.47: Задачи на выполненную работу (2 навыка) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G5_S47_01','L4','G5_P47','Productivity concept','Понимание производительности','A=p×t',1,'recall',5,5,
 'Что означает «выполнить за 1 час»?','Осмысление скорости работы','Medium (Level B)','A = p × t'),
('G5_S47_02','L4','G5_P47','Joint work','Совместная работа','Сложение производительностей',2,'analyze',5,5,
 'За сколько часов выполнят работу вместе?','Сложение производительностей','High (Level C)',NULL);

-- ============================================================================
-- ИТОГО: 126 навыков L4, каждый с example_task + assessed_ability + difficulty_level
-- ============================================================================
SELECT 'Grade 5 clean skeleton loaded!' as status;
SELECT level, COUNT(*) as cnt FROM knowledge_hierarchy WHERE id LIKE 'G5_%' GROUP BY level ORDER BY level;
