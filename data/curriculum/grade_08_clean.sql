-- ============================================================================
-- ALGO V1 — СКЕЛЕТ 8 КЛАСС (чистый методический файл)
-- Источник: Sardor Bozorov, PDF программа 8 класса
-- 4 разделов, 7 тем, 31 пунктов, 133 атомарных навыков
-- ============================================================================
-- ФОРМАТ: Только поля методиста. ИИ-поля (importance, typical_time_seconds,
-- irt_*, difficulty_score, weight, criticality) заполняются пайплайном.
-- Prerequisites — будут сгенерированы AI-пайплайном
-- ============================================================================

-- Очистка
DELETE FROM tasks_master WHERE skill_id LIKE 'G8_%';
DELETE FROM knowledge_hierarchy WHERE id LIKE 'G8_%';

-- ============================================================================
-- L1: РАЗДЕЛЫ (4)
-- ============================================================================
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, class_level_start, class_level_end, sequence_order)
VALUES
    ('G8_ALG',  'L1', NULL, 'Algebraic Expressions Root Power', 'Алгебраические выражения, корень, степень', 8, 8, 1),
    ('G8_INEQ',  'L1', NULL, 'Inequalities', 'Неравенства', 8, 8, 2),
    ('G8_QUAD',  'L1', NULL, 'Quadratic Equations', 'Квадратные уравнения', 8, 8, 3),
    ('G8_DATA',  'L1', NULL, 'Data Analysis', 'Анализ данных', 8, 8, 4);

-- ============================================================================
-- L2: ТЕМЫ (7)
-- ============================================================================
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, class_level_start, class_level_end, sequence_order)
VALUES
    ('G8_T01', 'L2', 'G8_ALG', 'Algebraic Fractions and Operations', 'Алгебраические дроби и действия над ними', 8, 8, 1),
    ('G8_T02', 'L2', 'G8_ALG', 'Function Power Root', 'Функция, степень, корень', 8, 8, 2),
    ('G8_T03', 'L2', 'G8_INEQ', 'Linear Inequalities', 'Линейные неравенства', 8, 8, 3),
    ('G8_T04', 'L2', 'G8_INEQ', 'Modulus and Approximations', 'Модуль и приближённые вычисления', 8, 8, 4),
    ('G8_T05', 'L2', 'G8_QUAD', 'All Types of Quadratic Equations', 'Все виды квадратных уравнений', 8, 8, 5),
    ('G8_T06', 'L2', 'G8_QUAD', 'Higher Degree Equations', 'Уравнения высших степеней', 8, 8, 6),
    ('G8_T07', 'L2', 'G8_DATA', 'Data and Combinatorics', 'Данные и комбинаторика', 8, 8, 7);

-- ============================================================================
-- L3: ПУНКТЫ (31)
-- ============================================================================
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, class_level_start, class_level_end, sequence_order)
VALUES
    -- Тема 1
    ('G8_P01', 'L3', 'G8_T01', 'Algebraic Expressions', 'Алгебраические выражения', 8, 8, 1),
    ('G8_P02', 'L3', 'G8_T01', 'Algebraic Fraction Reduction', 'Алгебраическая дробь. Сокращение дробей', 8, 8, 2),
    ('G8_P03', 'L3', 'G8_T01', 'Common Denominator', 'Приведение дробей к общему знаменателю', 8, 8, 3),
    ('G8_P04', 'L3', 'G8_T01', 'Add Sub Algebraic Fractions', 'Сложение и вычитание алгебраических дробей', 8, 8, 4),
    ('G8_P05', 'L3', 'G8_T01', 'Mul Div Algebraic Fractions', 'Умножение и деление алгебраических дробей', 8, 8, 5),
    ('G8_P06', 'L3', 'G8_T01', 'Identical Transformations of Rational Expressions', 'Замена дробно-рациональных выражений тождественными', 8, 8, 6),
    -- Тема 2
    ('G8_P07', 'L3', 'G8_T02', 'Function y equals k over x', 'Функция y = k/x. Её свойства и график', 8, 8, 7),
    ('G8_P08', 'L3', 'G8_T02', 'Arithmetic Root and Properties', 'Арифметический корень натуральной степени и его свойства', 8, 8, 8),
    ('G8_P09', 'L3', 'G8_T02', 'Rational Exponent', 'Степень с рациональным показателем и её свойства', 8, 8, 9),
    ('G8_P10', 'L3', 'G8_T02', 'Simplifying Expressions with Rational Exponents', 'Упрощение выражений со степенями с рациональным показателем', 8, 8, 10),
    -- Тема 3
    ('G8_P11', 'L3', 'G8_T03', 'Numeric Inequalities', 'Числовые неравенства', 8, 8, 11),
    ('G8_P12', 'L3', 'G8_T03', 'Properties of Numeric Inequalities', 'Основные свойства числовых неравенств', 8, 8, 12),
    ('G8_P13', 'L3', 'G8_T03', 'Addition and Multiplication of Inequalities', 'Сложение и умножение неравенств', 8, 8, 13),
    ('G8_P14', 'L3', 'G8_T03', 'Raising Inequalities to a Power', 'Возведение числовых неравенств в степень', 8, 8, 14),
    ('G8_P15', 'L3', 'G8_T03', 'Inequality with One Unknown', 'Неравенство с одним неизвестным', 8, 8, 15),
    ('G8_P16', 'L3', 'G8_T03', 'Systems of Inequalities and Intervals', 'Системы неравенств с одним неизвестным. Числовые промежутки', 8, 8, 16),
    -- Тема 4
    ('G8_P17', 'L3', 'G8_T04', 'Modulus Equations and Inequalities', 'Модуль числа. Уравнения и неравенства с модулем', 8, 8, 17),
    ('G8_P18', 'L3', 'G8_T04', 'Approximate Values and Error', 'Приближённые вычисления. Погрешность приближения', 8, 8, 18),
    ('G8_P19', 'L3', 'G8_T04', 'Error Estimation', 'Оценка погрешностей', 8, 8, 19),
    ('G8_P20', 'L3', 'G8_T04', 'Rounding Numbers', 'Округление чисел', 8, 8, 20),
    ('G8_P21', 'L3', 'G8_T04', 'Relative Error', 'Относительная погрешность', 8, 8, 21),
    -- Тема 5
    ('G8_P22', 'L3', 'G8_T05', 'Quadratic Equations and Roots', 'Квадратные уравнения и их корни', 8, 8, 22),
    ('G8_P23', 'L3', 'G8_T05', 'Incomplete Quadratic Equations', 'Неполные квадратные уравнения и их решение', 8, 8, 23),
    ('G8_P24', 'L3', 'G8_T05', 'Discriminant and Root Formulas', 'Формулы корней квадратного уравнения. Дискриминант', 8, 8, 24),
    ('G8_P25', 'L3', 'G8_T05', 'Vieta Theorem and Factoring', 'Теорема Виета. Разложение квадратного трёхчлена', 8, 8, 25),
    -- Тема 6
    ('G8_P26', 'L3', 'G8_T06', 'Biquadratic Equations', 'Биквадратные уравнения. Уравнения, сводящиеся к квадратным', 8, 8, 26),
    ('G8_P27', 'L3', 'G8_T06', 'Word Problems with Quadratic Equations', 'Решение задач с помощью квадратных уравнений', 8, 8, 27),
    -- Тема 7
    ('G8_P28', 'L3', 'G8_T07', 'Data Analysis and Representation', 'Анализ данных. Представление данных', 8, 8, 28),
    ('G8_P29', 'L3', 'G8_T07', 'Mean Mode Median', 'Среднее значение. Мода. Медиана', 8, 8, 29),
    ('G8_P30', 'L3', 'G8_T07', 'Enumeration Method', 'Решение комбинаторных задач методом перебора', 8, 8, 30),
    ('G8_P31', 'L3', 'G8_T07', 'Fundamental Counting Principle', 'Основной закон комбинаторики и его применение', 8, 8, 31);

-- ============================================================================
-- L4: АТОМАРНЫЕ НАВЫКИ (133)
-- Каждый навык содержит: example_task, assessed_ability, difficulty_level, formula из PDF
-- ============================================================================

-- ─── П.1: Алгебраические выражения (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S01_01','L4','G8_P01','Domain of expression','Определение ОДЗ','Найдите ОДЗ выражения 1/(x − 3)',1,'apply',8,8,
 'Найдите ОДЗ выражения 1/(x − 3)','Определение значений переменной, при которых выражение имеет смысл','Medium (Level B)',NULL),
('G8_S01_02','L4','G8_P01','Combine like terms','Приведение подобных членов','Упростите выражение 5x − 3x + 2',2,'recall',8,8,
 'Упростите выражение 5x − 3x + 2','Сложение коэффициентов при одинаковых переменных','Low (Level A)',NULL),
('G8_S01_03','L4','G8_P01','Expand brackets','Раскрытие скобок','Упростите 3(x − 2)',3,'apply',8,8,
 'Упростите 3(x − 2)','Применение распределительного свойства','Medium (Level B)','a(b−c)=ab−ac');

-- ─── П.2: Алгебраическая дробь. Сокращение дробей (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S02_01','L4','G8_P02','Identify algebraic fraction','Определение алгебраической дроби','Является ли выражение (x + 1)/2 алгебраической дробью',1,'recall',8,8,
 'Является ли выражение (x + 1)/2 алгебраической дробью','Распознавание дробного выражения','Low (Level A)',NULL),
('G8_S02_02','L4','G8_P02','Reduce numeric factors','Сокращение числовых множителей','Сократите дробь 6x/9',2,'apply',8,8,
 'Сократите дробь 6x/9','Деление числителя и знаменателя на общий множитель','Medium (Level B)',NULL),
('G8_S02_03','L4','G8_P02','Reduce using formulas','Сокращение с использованием формул','Сократите дробь (x² − 9)/(x − 3)',3,'analyze',8,8,
 'Сократите дробь (x² − 9)/(x − 3)','Применение формулы разности квадратов','High (Level C)','x²−9=(x−3)(x+3)');

-- ─── П.3: Приведение дробей к общему знаменателю (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S03_01','L4','G8_P03','Find common denominator','Нахождение общего знаменателя','Приведите к общему знаменателю дроби 1/x и 1/y',1,'apply',8,8,
 'Приведите к общему знаменателю дроби 1/x и 1/y','Построение общего знаменателя xy','Medium (Level B)',NULL),
('G8_S03_02','L4','G8_P03','Common denominator with factoring','Приведение дробей с разложением на множители','Приведите к общему знаменателю дроби 1/(x − 1) и 1/(x + 1)',2,'analyze',8,8,
 'Приведите к общему знаменателю дроби 1/(x − 1) и 1/(x + 1)','Формирование общего знаменателя (x − 1)(x + 1)','High (Level C)',NULL),
('G8_S03_03','L4','G8_P03','Complex denominators','Работа со сложными знаменателями','Приведите дроби 2/x и 3/(2x) к общему знаменателю',3,'analyze',8,8,
 'Приведите дроби 2/x и 3/(2x) к общему знаменателю','Корректное домножение числителя и знаменателя','High (Level C)',NULL);

-- ─── П.4: Сложение и вычитание алгебраических дробей (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S04_01','L4','G8_P04','Add fractions same denominator','Сложение дробей с одинаковым знаменателем','Сложите 3/x + 5/x',1,'apply',8,8,
 'Сложите 3/x + 5/x','Сложение числителей','Medium (Level B)','a/b+c/b=(a+c)/b'),
('G8_S04_02','L4','G8_P04','Subtract fractions same denominator','Вычитание дробей с одинаковым знаменателем','Вычтите 7/x − 2/x',2,'apply',8,8,
 'Вычтите 7/x − 2/x','Вычитание числителей','Medium (Level B)',NULL),
('G8_S04_03','L4','G8_P04','Add fractions different denominators','Сложение дробей с разными знаменателями','Сложите 1/x + 1/(x + 1)',3,'analyze',8,8,
 'Сложите 1/x + 1/(x + 1)','Приведение к общему знаменателю и объединение дробей','High (Level C)',NULL);

-- ─── П.5: Умножение и деление алгебраических дробей (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S05_01','L4','G8_P05','Multiply fractions','Умножение дробей','Перемножьте (2/x) · (3/y)',1,'apply',8,8,
 'Перемножьте (2/x) · (3/y)','Перемножение числителей и знаменателей','Medium (Level B)','(a/b)·(c/d)=ac/(bd)'),
('G8_S05_02','L4','G8_P05','Divide fractions','Деление дробей','Разделите (4/x) : (2/y)',2,'analyze',8,8,
 'Разделите (4/x) : (2/y)','Переход к умножению на обратную дробь','High (Level C)','(a/b):(c/d)=(a/b)·(d/c)'),
('G8_S05_03','L4','G8_P05','Reduce after multiplication','Сокращение после умножения','Упростите (6x/5) · (5/(3x))',3,'analyze',8,8,
 'Упростите (6x/5) · (5/(3x))','Сокращение переменных и коэффициентов','High (Level C)',NULL);

-- ─── П.6: Замена дробно-рациональных выражений тождественными (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S06_01','L4','G8_P06','Transform rational expression','Преобразование дробного выражения','Упростите выражение (x² − 9)/(x − 3)',1,'apply',8,8,
 'Упростите выражение (x² − 9)/(x − 3)','Применение формулы разности квадратов','Medium (Level B)','a²−b²=(a−b)(a+b)'),
('G8_S06_02','L4','G8_P06','Replace with identical expression','Замена выражения тождественным','Упростите (x² − 4)/(x − 2)',2,'analyze',8,8,
 'Упростите (x² − 4)/(x − 2)','Разложение числителя и сокращение дроби','High (Level C)',NULL),
('G8_S06_03','L4','G8_P06','Complex rational expressions','Работа со сложными выражениями','Упростите (x² − 1)/(x² − x)',3,'analyze',8,8,
 'Упростите (x² − 1)/(x² − x)','Разложение на множители и сокращение','High (Level C)',NULL);

-- ─── П.7: Функция y = k/x. Её свойства и график (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S07_01','L4','G8_P07','Compute function value','Вычисление значения функции','Найдите значение функции y = 6/x при x = 2',1,'apply',8,8,
 'Найдите значение функции y = 6/x при x = 2','Подстановка значения переменной','Medium (Level B)','y=k/x'),
('G8_S07_02','L4','G8_P07','Domain of function','Определение ОДЗ функции','Найдите ОДЗ функции y = 5/x',2,'apply',8,8,
 'Найдите ОДЗ функции y = 5/x','Определение запрета деления на ноль','Medium (Level B)',NULL),
('G8_S07_03','L4','G8_P07','Determine quadrants','Определение четвертей графика','В каких четвертях расположен график функции y = −4/x',3,'analyze',8,8,
 'В каких четвертях расположен график функции y = −4/x','Анализ знака коэффициента k','High (Level C)',NULL);

-- ─── П.8: Арифметический корень натуральной степени и его свойства (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S08_01','L4','G8_P08','Compute root','Вычисление корня','Найдите √49',1,'recall',8,8,
 'Найдите √49','Извлечение квадратного корня','Low (Level A)',NULL),
('G8_S08_02','L4','G8_P08','Root properties','Использование свойств корня','Найдите √(16·9)',2,'apply',8,8,
 'Найдите √(16·9)','Применение свойства произведения','Medium (Level B)','√(ab)=√a·√b'),
('G8_S08_03','L4','G8_P08','Simplify root expression','Упрощение выражения','Упростите √(36x²)',3,'analyze',8,8,
 'Упростите √(36x²)','Извлечение корня из коэффициента и степени','High (Level C)',NULL);

-- ─── П.9: Степень с рациональным показателем и её свойства (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S09_01','L4','G8_P09','Convert to root','Переход к корню','Представьте 16^(1/2) в виде корня',1,'apply',8,8,
 'Представьте 16^(1/2) в виде корня','Переход от степени к корню','Medium (Level B)','a^(m/n)=ⁿ√(aᵐ)'),
('G8_S09_02','L4','G8_P09','Compute rational power','Вычисление степени','Найдите 27^(1/3)',2,'apply',8,8,
 'Найдите 27^(1/3)','Извлечение кубического корня','Medium (Level B)',NULL),
('G8_S09_03','L4','G8_P09','Apply power properties','Применение свойств степени','Упростите a^(1/2) · a^(1/2)',3,'analyze',8,8,
 'Упростите a^(1/2) · a^(1/2)','Сложение показателей степени','High (Level C)','aᵐ·aⁿ=aᵐ⁺ⁿ');

-- ─── П.10: Упрощение выражений со степенями с рациональным показателем (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S10_01','L4','G8_P10','Simplify power of power','Упрощение степени','Упростите (x^(1/2))²',1,'apply',8,8,
 'Упростите (x^(1/2))²','Применение свойства (aᵐ)ⁿ = aᵐⁿ','Medium (Level B)','(aᵐ)ⁿ=aᵐⁿ'),
('G8_S10_02','L4','G8_P10','Fractional exponents','Работа с дробными показателями','Упростите x^(3/2)/x^(1/2)',2,'analyze',8,8,
 'Упростите x^(3/2)/x^(1/2)','Вычитание показателей степеней','High (Level C)',NULL),
('G8_S10_03','L4','G8_P10','Full simplification','Полное упрощение выражения','Упростите (x^(1/2) · x^(3/2))/x',3,'analyze',8,8,
 'Упростите (x^(1/2) · x^(3/2))/x','Последовательное применение свойств степеней','High (Level C)',NULL);

-- ─── П.11: Числовые неравенства (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S11_01','L4','G8_P11','Compare numbers','Сравнение чисел','Сравните числа 7 и 5',1,'recall',8,8,
 'Сравните числа 7 и 5','Определение отношения «больше» или «меньше»','Low (Level A)',NULL),
('G8_S11_02','L4','G8_P11','Write inequality','Запись неравенства','Запишите неравенство для утверждения: число 12 больше 8',2,'recall',8,8,
 'Запишите неравенство для утверждения: число 12 больше 8','Корректная запись знаков неравенства','Low (Level A)',NULL),
('G8_S11_03','L4','G8_P11','Check inequality','Проверка истинности неравенства','Верно ли неравенство 3² > 8',3,'apply',8,8,
 'Верно ли неравенство 3² > 8','Вычисление и сравнение значений','Medium (Level B)',NULL);

-- ─── П.12: Основные свойства числовых неравенств (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S12_01','L4','G8_P12','Add to both sides','Прибавление числа к обеим частям','Если 5 > 3, верно ли 5 + 2 > 3 + 2',1,'apply',8,8,
 'Если 5 > 3, верно ли 5 + 2 > 3 + 2','Применение свойства сложения неравенств','Medium (Level B)',NULL),
('G8_S12_02','L4','G8_P12','Multiply by positive','Умножение на положительное число','Если 4 > 2, сравните 4·3 и 2·3',2,'apply',8,8,
 'Если 4 > 2, сравните 4·3 и 2·3','Сохранение знака неравенства','Medium (Level B)',NULL),
('G8_S12_03','L4','G8_P12','Multiply by negative','Умножение на отрицательное число','Если 4 > 2, сравните −4 и −2',3,'analyze',8,8,
 'Если 4 > 2, сравните −4 и −2','Изменение знака неравенства','High (Level C)',NULL);

-- ─── П.13: Сложение и умножение неравенств (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S13_01','L4','G8_P13','Add inequalities','Сложение неравенств','Если 5 > 3 и 4 > 2, сравните 5 + 4 и 3 + 2',1,'apply',8,8,
 'Если 5 > 3 и 4 > 2, сравните 5 + 4 и 3 + 2','Применение правила сложения неравенств','Medium (Level B)',NULL),
('G8_S13_02','L4','G8_P13','Multiply inequality by number','Умножение неравенства на число','Если 6 > 2, сравните 6·4 и 2·4',2,'apply',8,8,
 'Если 6 > 2, сравните 6·4 и 2·4','Умножение обеих частей неравенства','Medium (Level B)',NULL),
('G8_S13_03','L4','G8_P13','Multiply by negative number','Умножение неравенства на отрицательное число','Если 5 > 2, сравните −5 и −2',3,'analyze',8,8,
 'Если 5 > 2, сравните −5 и −2','Изменение направления знака','High (Level C)',NULL);

-- ─── П.14: Возведение числовых неравенств в степень (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S14_01','L4','G8_P14','Square both sides','Возведение в квадрат','Если 4 > 3, сравните 4² и 3²',1,'apply',8,8,
 'Если 4 > 3, сравните 4² и 3²','Возведение обеих частей неравенства в степень','Medium (Level B)',NULL),
('G8_S14_02','L4','G8_P14','Analyze sign','Анализ знака числа','Можно ли возвести в квадрат неравенство −5 > −7',2,'analyze',8,8,
 'Можно ли возвести в квадрат неравенство −5 > −7','Анализ условий применения правила','High (Level C)',NULL),
('G8_S14_03','L4','G8_P14','Compare powers','Сравнение степеней','Сравните 2³ и 3²',3,'apply',8,8,
 'Сравните 2³ и 3²','Вычисление степеней и сравнение','Medium (Level B)',NULL);

-- ─── П.15: Неравенство с одним неизвестным (11 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S15_01','L4','G8_P15','Solve simple inequality','Решение простого неравенства','Решите неравенство x + 4 > 9',1,'apply',8,8,
 'Решите неравенство x + 4 > 9','Перенос числа в другую часть','Medium (Level B)',NULL),
('G8_S15_02','L4','G8_P15','Solve with multiplication','Решение неравенства с умножением','Решите 3x > 12',2,'apply',8,8,
 'Решите 3x > 12','Деление обеих частей на число','Medium (Level B)',NULL),
('G8_S15_03','L4','G8_P15','Sign change on negative division','Изменение знака при делении на отрицательное число','Решите −2x > 6',3,'analyze',8,8,
 'Решите −2x > 6','Изменение знака неравенства при делении','High (Level C)',NULL),
('G8_S15_04','L4','G8_P15','Expression positive','Определение при каких значениях выражение положительно','Определите, при каких значениях x положительно выражение 3x − 5',4,'apply',8,8,
 'Определите, при каких значениях x положительно выражение 3x − 5','Переход от условия «выражение положительно» к неравенству','Medium (Level B)',NULL),
('G8_S15_05','L4','G8_P15','Expression negative','Определение при каких значениях выражение отрицательно','Определите, при каких значениях y отрицательно выражение 5 − 2y',5,'apply',8,8,
 'Определите, при каких значениях y отрицательно выражение 5 − 2y','Составление и решение неравенства вида 5 − 2y < 0','Medium (Level B)',NULL),
('G8_S15_06','L4','G8_P15','Solve after expanding brackets','Решение неравенства после раскрытия скобок','Решите неравенство 2(x + 3) + 3x > 0',6,'analyze',8,8,
 'Решите неравенство 2(x + 3) + 3x > 0','Раскрытие скобок, приведение подобных и решение линейного неравенства','High (Level C)',NULL),
('G8_S15_07','L4','G8_P15','Fractional coefficients','Решение неравенства с дробными коэффициентами','Решите неравенство 5/2 − 4x > 0',7,'analyze',8,8,
 'Решите неравенство 5/2 − 4x > 0','Работа с дробными числами в линейном неравенстве','High (Level C)',NULL),
('G8_S15_08','L4','G8_P15','Smallest integer solution','Определение наименьшего целого решения','Найдите наименьшее целое число, удовлетворяющее неравенству 4(y − 1) < 2 + 7y',8,'analyze',8,8,
 'Найдите наименьшее целое число, удовлетворяющее неравенству 4(y − 1) < 2 + 7y','Решение неравенства и выбор наименьшего целого числа из множества решений','High (Level C)',NULL),
('G8_S15_09','L4','G8_P15','Largest integer solution','Определение наибольшего целого решения','Найдите наибольшее целое число, удовлетворяющее неравенству 5 − 2x > 0',9,'analyze',8,8,
 'Найдите наибольшее целое число, удовлетворяющее неравенству 5 − 2x > 0','Решение неравенства и выбор наибольшего целого числа из множества решений','High (Level C)',NULL),
('G8_S15_10','L4','G8_P15','Compare fractional expressions','Сравнение дробных выражений с переменной','Для каких значений a дробь a/3 больше дроби (a + 1)/4',10,'analyze',8,8,
 'Для каких значений a дробь a/3 больше дроби (a + 1)/4','Составление линейного неравенства из условия сравнения двух дробей','High (Level C)',NULL),
('G8_S15_11','L4','G8_P15','Compare compound fractions','Сравнение выражения с разностью дробей','Для каких значений x дробь (3x − 5)/6 больше разности дробей (6x − 7)/15 и (3 − x)/9',11,'analyze',8,8,
 'Для каких значений x дробь (3x − 5)/6 больше разности дробей (6x − 7)/15 и (3 − x)/9','Преобразование составного неравенства с дробными выражениями','High (Level C)',NULL);

-- ─── П.16: Системы неравенств с одним неизвестным. Числовые промежутки (10 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S16_01','L4','G8_P16','Solve simple inequality interval','Решение простого неравенства','Решите неравенство x > 3',1,'apply',8,8,
 'Решите неравенство x > 3','Определение множества решений и запись в виде промежутка (3; +∞)','Medium (Level B)',NULL),
('G8_S16_02','L4','G8_P16','Solve system of inequalities','Решение системы неравенств','Решите систему x > 2, x < 7',2,'apply',8,8,
 'Решите систему x > 2, x < 7','Нахождение пересечения решений','Medium (Level B)',NULL),
('G8_S16_03','L4','G8_P16','System with included bounds','Решение системы с включёнными границами','Решите систему x ≥ 1, x ≤ 5',3,'apply',8,8,
 'Решите систему x ≥ 1, x ≤ 5','Запись решения в виде отрезка','Medium (Level B)',NULL),
('G8_S16_04','L4','G8_P16','System with brackets','Решение системы линейных неравенств со скобками','Решите систему 5x − 1 > 3(x + 1), 2(x + 4) > x + 5',4,'analyze',8,8,
 'Решите систему 5x − 1 > 3(x + 1), 2(x + 4) > x + 5','Раскрытие скобок, решение каждого неравенства и нахождение пересечения','High (Level C)',NULL),
('G8_S16_05','L4','G8_P16','System with fractions','Решение системы с дробными коэффициентами','Решите систему 5x/12 + 4/3 ≥ (x + 1)/3, 2 − 5x/14 < (2 − x)/2',5,'analyze',8,8,
 'Решите систему 5x/12 + 4/3 ≥ (x + 1)/3, 2 − 5x/14 < (2 − x)/2','Освобождение от дробей, решение линейных неравенств','High (Level C)',NULL),
('G8_S16_06','L4','G8_P16','Graph solution on number line','Изображение решения на числовой прямой','Изобразите на числовой прямой решение системы x ≥ −12, x < −7',6,'analyze',8,8,
 'Изобразите на числовой прямой решение системы x ≥ −12, x < −7','Графическое представление пересечения множеств решений','High (Level C)',NULL),
('G8_S16_07','L4','G8_P16','Write answer as interval','Запись ответа в виде числового промежутка','Запишите множество решений системы x > −3, x ≤ 2 в виде промежутка',7,'apply',8,8,
 'Запишите множество решений системы x > −3, x ≤ 2 в виде промежутка','Переход от двойного неравенства к интервальной записи','Medium (Level B)',NULL),
('G8_S16_08','L4','G8_P16','Check if system has solutions','Проверка наличия решений системы','Решите систему x > 5, x < 2',8,'apply',8,8,
 'Решите систему x > 5, x < 2','Определение пустого множества решений','Medium (Level B)',NULL),
('G8_S16_09','L4','G8_P16','Common interval','Система неравенств с общим промежутком','Решите систему 3x − 2 ≥ 1, 2x + 5 < 11',9,'analyze',8,8,
 'Решите систему 3x − 2 ≥ 1, 2x + 5 < 11','Решение двух линейных неравенств и нахождение общего промежутка','High (Level C)',NULL),
('G8_S16_10','L4','G8_P16','Prove system has solution','Доказательство по системе неравенств','Покажите, что система 2(1 − x) < 4 − 3x, 10 − 3x < 1 имеет решение',10,'analyze',8,8,
 'Покажите, что система 2(1 − x) < 4 − 3x, 10 − 3x < 1 имеет решение','Решение обоих неравенств и анализ пересечения решений','High (Level C)',NULL);

-- ─── П.17: Модуль числа. Уравнения и неравенства с модулем (4 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S17_01','L4','G8_P17','Compute modulus','Вычисление модуля','Найдите |−7|',1,'recall',8,8,
 'Найдите |−7|','Понимание определения модуля','Low (Level A)','|x|={x, если x≥0; −x, если x<0}'),
('G8_S17_02','L4','G8_P17','Simple modulus equation','Решение простого уравнения с модулем','Решите |x| = 6',2,'apply',8,8,
 'Решите |x| = 6','Использование правила |x| = a → x = a или x = −a','Medium (Level B)',NULL),
('G8_S17_03','L4','G8_P17','Modulus equation with shift','Решение уравнения вида |x − a| = b','Решите |x − 3| = 5',3,'analyze',8,8,
 'Решите |x − 3| = 5','Применение формулы |x − a| = b → x = a ± b','High (Level C)','|x−a|=b → x=a±b'),
('G8_S17_04','L4','G8_P17','Modulus inequality','Решение неравенства с модулем','Решите |x| < 4',4,'analyze',8,8,
 'Решите |x| < 4','Преобразование неравенства |x| < a → −a < x < a','High (Level C)','|x|<a → −a<x<a');

-- ─── П.18: Приближённые вычисления. Погрешность приближения (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S18_01','L4','G8_P18','Approximate value','Определение приближённого значения','Запишите приближённое значение числа π с точностью до сотых',1,'recall',8,8,
 'Запишите приближённое значение числа π с точностью до сотых','Округление числа','Low (Level A)',NULL),
('G8_S18_02','L4','G8_P18','Absolute error','Нахождение абсолютной погрешности','Найдите погрешность, если точное значение 5.28, а приближённое 5.3',2,'apply',8,8,
 'Найдите погрешность, если точное значение 5.28, а приближённое 5.3','Применение формулы абсолютной погрешности','Medium (Level B)','Δ=|a−a₀|'),
('G8_S18_03','L4','G8_P18','Measurement accuracy','Определение точности измерения','Число 7.4 получено округлением. Найдите возможную погрешность',3,'analyze',8,8,
 'Число 7.4 получено округлением. Найдите возможную погрешность','Понимание интервала возможных значений','High (Level C)',NULL);

-- ─── П.19: Оценка погрешностей (2 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S19_01','L4','G8_P19','Compute absolute error','Определение абсолютной погрешности','Точное значение 8.37, приближённое 8.4. Найдите погрешность',1,'apply',8,8,
 'Точное значение 8.37, приближённое 8.4. Найдите погрешность','Вычисление абсолютной погрешности','Medium (Level B)','Δ=|a−a₀|'),
('G8_S19_02','L4','G8_P19','Value interval','Определение интервала точного значения','Число 6.3 округлено до десятых. Найдите возможный интервал значений',2,'analyze',8,8,
 'Число 6.3 округлено до десятых. Найдите возможный интервал значений','Определение границ погрешности','High (Level C)',NULL);

-- ─── П.20: Округление чисел (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S20_01','L4','G8_P20','Round to tenths','Округление до десятых','Округлите 4.27 до десятых',1,'recall',8,8,
 'Округлите 4.27 до десятых','Применение правила округления','Low (Level A)',NULL),
('G8_S20_02','L4','G8_P20','Round to hundredths','Округление до сотых','Округлите 6.378 до сотых',2,'apply',8,8,
 'Округлите 6.378 до сотых','Анализ следующего разряда','Medium (Level B)',NULL),
('G8_S20_03','L4','G8_P20','Round large numbers','Округление больших чисел','Округлите 5784 до сотен',3,'apply',8,8,
 'Округлите 5784 до сотен','Округление целых чисел','Medium (Level B)',NULL);

-- ─── П.21: Относительная погрешность (2 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S21_01','L4','G8_P21','Relative error','Нахождение относительной погрешности','Точное значение 10, приближённое 9.8. Найдите относительную погрешность',1,'analyze',8,8,
 'Точное значение 10, приближённое 9.8. Найдите относительную погрешность','Применение формулы относительной погрешности','High (Level C)','δ=|a−a₀|/|a|'),
('G8_S21_02','L4','G8_P21','Relative error in percent','Запись относительной погрешности в процентах','Выразите относительную погрешность 0.02 в процентах',2,'analyze',8,8,
 'Выразите относительную погрешность 0.02 в процентах','Перевод десятичной дроби в проценты','High (Level C)',NULL);

-- ─── П.22: Квадратные уравнения и их корни (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S22_01','L4','G8_P22','Recognize quadratic equation','Распознавание квадратного уравнения','Является ли уравнение 3x² − 5x + 2 = 0 квадратным',1,'recall',8,8,
 'Является ли уравнение 3x² − 5x + 2 = 0 квадратным','Определение уравнения вида ax² + bx + c = 0','Low (Level A)','ax²+bx+c=0'),
('G8_S22_02','L4','G8_P22','Identify coefficients','Определение коэффициентов a, b, c','Найдите коэффициенты a, b, c в уравнении 2x² + 7x − 4 = 0',2,'recall',8,8,
 'Найдите коэффициенты a, b, c в уравнении 2x² + 7x − 4 = 0','Выделение коэффициентов квадратного уравнения','Low (Level A)',NULL),
('G8_S22_03','L4','G8_P22','Check if number is root','Проверка, является ли число корнем','Является ли число x = 2 корнем уравнения x² − 3x + 2 = 0',3,'apply',8,8,
 'Является ли число x = 2 корнем уравнения x² − 3x + 2 = 0','Подстановка числа в уравнение и проверка равенства нулю','Medium (Level B)',NULL),
('G8_S22_04','L4','G8_P22','Number of roots','Определение числа корней','Сколько корней может иметь квадратное уравнение',4,'apply',8,8,
 'Сколько корней может иметь квадратное уравнение','Понимание, что квадратное уравнение может иметь 2, 1 или 0 действительных корней','Medium (Level B)',NULL),
('G8_S22_05','L4','G8_P22','Reduce to standard form','Приведение к стандартному виду','Приведите уравнение x(x + 3) = 4 к виду ax² + bx + c = 0',5,'analyze',8,8,
 'Приведите уравнение x(x + 3) = 4 к виду ax² + bx + c = 0','Раскрытие скобок и перенос всех членов в одну часть','High (Level C)',NULL);

-- ─── П.23: Неполные квадратные уравнения и их решение (6 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S23_01','L4','G8_P23','Solve ax²=0','Решение уравнения вида ax² = 0','Решите уравнение 5x² = 0',1,'recall',8,8,
 'Решите уравнение 5x² = 0','Нахождение единственного корня x = 0','Low (Level A)',NULL),
('G8_S23_02','L4','G8_P23','Solve ax²+bx=0','Решение уравнения вида ax² + bx = 0','Решите уравнение x² − 6x = 0',2,'apply',8,8,
 'Решите уравнение x² − 6x = 0','Вынесение общего множителя x за скобку','Medium (Level B)',NULL),
('G8_S23_03','L4','G8_P23','Solve ax²+c=0','Решение уравнения вида ax² + c = 0','Решите уравнение x² − 16 = 0',3,'apply',8,8,
 'Решите уравнение x² − 16 = 0','Переход к виду x² = a и извлечение квадратного корня','Medium (Level B)',NULL),
('G8_S23_04','L4','G8_P23','Check for real roots','Определение наличия корней','Имеет ли уравнение x² + 9 = 0 действительные корни',4,'apply',8,8,
 'Имеет ли уравнение x² + 9 = 0 действительные корни','Анализ знака правой части при переходе к x² = −9','Medium (Level B)',NULL),
('G8_S23_05','L4','G8_P23','Solve after transformations','Решение неполного уравнения после преобразований','Решите уравнение 2x(x − 3) = 0',5,'analyze',8,8,
 'Решите уравнение 2x(x − 3) = 0','Применение свойства произведения, равного нулю','High (Level C)',NULL),
('G8_S23_06','L4','G8_P23','Reduce to incomplete quadratic','Приведение к неполному квадратному','Решите уравнение 3x² = 27',6,'apply',8,8,
 'Решите уравнение 3x² = 27','Выделение x² и извлечение корня','Medium (Level B)',NULL);

-- ─── П.24: Формулы корней квадратного уравнения. Дискриминант (7 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S24_01','L4','G8_P24','Compute discriminant','Вычисление дискриминанта','Найдите дискриминант уравнения x² − 5x + 6 = 0',1,'apply',8,8,
 'Найдите дискриминант уравнения x² − 5x + 6 = 0','Подстановка коэффициентов в формулу D = b² − 4ac','Medium (Level B)','D=b²−4ac'),
('G8_S24_02','L4','G8_P24','Number of roots by discriminant','Определение количества корней по дискриминанту','Определите число корней уравнения 2x² + 4x + 2 = 0',2,'apply',8,8,
 'Определите число корней уравнения 2x² + 4x + 2 = 0','Анализ значения дискриминанта','Medium (Level B)',NULL),
('G8_S24_03','L4','G8_P24','Find two roots','Нахождение двух корней','Решите уравнение x² − 7x + 12 = 0',3,'analyze',8,8,
 'Решите уравнение x² − 7x + 12 = 0','Применение полной формулы корней','High (Level C)','x=(-b±√D)/2a'),
('G8_S24_04','L4','G8_P24','One root when D=0','Нахождение одного корня при D = 0','Решите уравнение x² − 6x + 9 = 0',4,'analyze',8,8,
 'Решите уравнение x² − 6x + 9 = 0','Решение квадратного уравнения при нулевом дискриминанте','High (Level C)',NULL),
('G8_S24_05','L4','G8_P24','No real roots D<0','Определение отсутствия действительных корней','Решите уравнение x² + 2x + 5 = 0',5,'analyze',8,8,
 'Решите уравнение x² + 2x + 5 = 0','Вывод о том, что при D < 0 действительных корней нет','High (Level C)',NULL),
('G8_S24_06','L4','G8_P24','Careful sign work','Аккуратная работа со знаками','Решите уравнение 3x² + x − 2 = 0',6,'analyze',8,8,
 'Решите уравнение 3x² + x − 2 = 0','Точная подстановка коэффициентов и вычисление корней','High (Level C)',NULL),
('G8_S24_07','L4','G8_P24','Solve after reducing to standard form','Решение после приведения к стандартному виду','Решите уравнение 2x(x − 1) = 3',7,'analyze',8,8,
 'Решите уравнение 2x(x − 1) = 3','Преобразование к виду ax² + bx + c = 0 и решение через дискриминант','High (Level C)',NULL);

-- ─── П.25: Теорема Виета. Разложение квадратного трёхчлена (6 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S25_01','L4','G8_P25','Find roots by Vieta','Нахождение корней по теореме Виета','Найдите корни уравнения x² − 5x + 6 = 0 по теореме Виета',1,'apply',8,8,
 'Найдите корни уравнения x² − 5x + 6 = 0 по теореме Виета','Подбор двух чисел по сумме и произведению','Medium (Level B)','x₁+x₂=−p, x₁x₂=q'),
('G8_S25_02','L4','G8_P25','Check pair by Vieta','Проверка пары чисел по теореме Виета','Являются ли числа 2 и 3 корнями уравнения x² − 5x + 6 = 0',2,'apply',8,8,
 'Являются ли числа 2 и 3 корнями уравнения x² − 5x + 6 = 0','Проверка суммы и произведения корней','Medium (Level B)',NULL),
('G8_S25_03','L4','G8_P25','Compose equation from roots','Составление квадратного уравнения по корням','Составьте квадратное уравнение, если его корни 2 и 5',3,'analyze',8,8,
 'Составьте квадратное уравнение, если его корни 2 и 5','Переход от корней к уравнению','High (Level C)','x²−(x₁+x₂)x+x₁x₂=0'),
('G8_S25_04','L4','G8_P25','Factor trinomial by roots','Разложение квадратного трёхчлена на множители','Разложите на множители x² − 7x + 12',4,'analyze',8,8,
 'Разложите на множители x² − 7x + 12','Представление трёхчлена в виде (x − x₁)(x − x₂)','High (Level C)','ax²+bx+c=a(x−x₁)(x−x₂)'),
('G8_S25_05','L4','G8_P25','Factor with leading coefficient','Разложение с коэффициентом при x²','Разложите на множители 2x² − 5x + 2',5,'analyze',8,8,
 'Разложите на множители 2x² − 5x + 2','Учёт коэффициента a при разложении','High (Level C)',NULL),
('G8_S25_06','L4','G8_P25','Find coefficient from root condition','Нахождение коэффициента по условию о корнях','При каком значении k уравнение x² + kx + 6 = 0 имеет корни 2 и 3',6,'analyze',8,8,
 'При каком значении k уравнение x² + kx + 6 = 0 имеет корни 2 и 3','Применение суммы корней по теореме Виета','High (Level C)',NULL);

-- ─── П.26: Биквадратные уравнения. Уравнения, сводящиеся к квадратным (6 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S26_01','L4','G8_P26','Recognize biquadratic','Распознавание биквадратного уравнения','Является ли уравнение x⁴ − 5x² + 4 = 0 биквадратным',1,'recall',8,8,
 'Является ли уравнение x⁴ − 5x² + 4 = 0 биквадратным','Определение уравнения по степеням x⁴ и x²','Low (Level A)','ax⁴+bx²+c=0'),
('G8_S26_02','L4','G8_P26','Variable substitution','Замена переменной','Сделайте замену t = x² в уравнении x⁴ − 5x² + 4 = 0',2,'apply',8,8,
 'Сделайте замену t = x² в уравнении x⁴ − 5x² + 4 = 0','Переход от биквадратного уравнения к квадратному','Medium (Level B)','t=x²'),
('G8_S26_03','L4','G8_P26','Full solution of biquadratic','Полное решение биквадратного уравнения','Решите уравнение x⁴ − 5x² + 4 = 0',3,'analyze',8,8,
 'Решите уравнение x⁴ − 5x² + 4 = 0','Решение через замену и обратный переход к x','High (Level C)',NULL),
('G8_S26_04','L4','G8_P26','Select real roots only','Отбор только действительных корней','Решите уравнение x⁴ − 13x² + 36 = 0',4,'analyze',8,8,
 'Решите уравнение x⁴ − 13x² + 36 = 0','Решение квадратного уравнения по t и анализ значений x²','High (Level C)',NULL),
('G8_S26_05','L4','G8_P26','Equation reducing to quadratic','Уравнение, сводящееся к квадратному','Решите уравнение (x² − 1)² − 5(x² − 1) + 6 = 0',5,'analyze',8,8,
 'Решите уравнение (x² − 1)² − 5(x² − 1) + 6 = 0','Введение новой переменной для всего выражения','High (Level C)',NULL),
('G8_S26_06','L4','G8_P26','Factor and reduce to quadratic','Уравнение с вынесением общего множителя','Решите уравнение x⁴ − 4x² = 0',6,'analyze',8,8,
 'Решите уравнение x⁴ − 4x² = 0','Выбор удобного способа — вынесение x² или замена t = x²','High (Level C)',NULL);

-- ─── П.27: Решение задач с помощью квадратных уравнений (6 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S27_01','L4','G8_P27','Consecutive numbers problem','Задача на последовательные числа','Произведение двух последовательных натуральных чисел равно 72. Найдите числа',1,'apply',8,8,
 'Произведение двух последовательных натуральных чисел равно 72. Найдите числа','Составление квадратного уравнения по условию задачи','Medium (Level B)',NULL),
('G8_S27_02','L4','G8_P27','Rectangle problem','Задача на прямоугольник','Площадь прямоугольника равна 48 см², а одна сторона на 2 см больше другой. Найдите стороны',2,'analyze',8,8,
 'Площадь прямоугольника равна 48 см², а одна сторона на 2 см больше другой. Найдите стороны','Составление модели через произведение сторон','High (Level C)',NULL),
('G8_S27_03','L4','G8_P27','Motion problem','Задача на движение','Автомобиль проехал 180 км. Увеличив скорость на 10 км/ч, затратил на 1 час меньше. Найдите скорость',3,'analyze',8,8,
 'Автомобиль проехал 180 км. Увеличив скорость на 10 км/ч, затратил на 1 час меньше. Найдите скорость','Составление дробно-рационального уравнения, сводящегося к квадратному','High (Level C)',NULL),
('G8_S27_04','L4','G8_P27','Sum and product problem','Задача на число по сумме и произведению','Сумма двух чисел равна 11, а их произведение равно 24. Найдите числа',4,'analyze',8,8,
 'Сумма двух чисел равна 11, а их произведение равно 24. Найдите числа','Составление квадратного уравнения по условиям суммы и произведения','High (Level C)',NULL),
('G8_S27_05','L4','G8_P27','Select root by meaning','Отбор корня по смыслу задачи','Решите задачу, если уравнение имеет два корня, но один не подходит по условию',5,'analyze',8,8,
 'Решите задачу, если уравнение имеет два корня, но один не подходит по условию','Проверка корней и выбор физически возможного ответа','High (Level C)',NULL),
('G8_S27_06','L4','G8_P27','Geometry to algebra','Составление уравнения по геометрическому условию','Диагональ прямоугольника равна 13, а одна сторона на 7 больше другой. Найдите стороны',6,'analyze',8,8,
 'Диагональ прямоугольника равна 13, а одна сторона на 7 больше другой. Найдите стороны','Перевод геометрической ситуации в алгебраическую модель','High (Level C)',NULL);

-- ─── П.28: Анализ данных. Представление данных (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S28_01','L4','G8_P28','Present data in table','Представление данных в таблице','Запишите в таблицу данные о количестве проданных книг за 5 дней: 8, 10, 7, 12, 9',1,'recall',8,8,
 'Запишите в таблицу данные о количестве проданных книг за 5 дней: 8, 10, 7, 12, 9','Структурирование данных','Low (Level A)',NULL),
('G8_S28_02','L4','G8_P28','Build bar chart','Построение столбчатой диаграммы','Постройте столбчатую диаграмму по данным: 4, 6, 5, 8, 7',2,'apply',8,8,
 'Постройте столбчатую диаграмму по данным: 4, 6, 5, 8, 7','Графическое представление числовых данных','Medium (Level B)',NULL),
('G8_S28_03','L4','G8_P28','Read data from chart','Чтение данных по диаграмме','Определите по диаграмме, в какой день продажи были наибольшими',3,'apply',8,8,
 'Определите по диаграмме, в какой день продажи были наибольшими','Анализ графического представления данных','Medium (Level B)',NULL),
('G8_S28_04','L4','G8_P28','Determine data trend','Определение тенденции данных','По данным 3, 5, 7, 9, 11 определите, увеличивается или уменьшается величина',4,'apply',8,8,
 'По данным 3, 5, 7, 9, 11 определите, увеличивается или уменьшается величина','Выявление закономерности в числовом ряду','Medium (Level B)',NULL),
('G8_S28_05','L4','G8_P28','Interpret data','Интерпретация данных','По таблице результатов теста определите средний результат класса',5,'analyze',8,8,
 'По таблице результатов теста определите средний результат класса','Использование данных для выводов','High (Level C)',NULL);

-- ─── П.29: Среднее значение. Мода. Медиана (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S29_01','L4','G8_P29','Arithmetic mean','Нахождение среднего арифметического','Найдите среднее арифметическое чисел 6, 8, 10, 12',1,'apply',8,8,
 'Найдите среднее арифметическое чисел 6, 8, 10, 12','Применение формулы среднего значения','Medium (Level B)','x̄=(x₁+x₂+...+xₙ)/n'),
('G8_S29_02','L4','G8_P29','Find mode','Нахождение моды','Найдите моду ряда 3, 5, 5, 6, 7, 7, 7, 8',2,'recall',8,8,
 'Найдите моду ряда 3, 5, 5, 6, 7, 7, 7, 8','Определение наиболее часто встречающегося значения','Low (Level A)',NULL),
('G8_S29_03','L4','G8_P29','Median odd count','Нахождение медианы при нечётном количестве данных','Найдите медиану ряда 2, 4, 5, 7, 9',3,'apply',8,8,
 'Найдите медиану ряда 2, 4, 5, 7, 9','Определение центрального элемента упорядоченного ряда','Medium (Level B)',NULL),
('G8_S29_04','L4','G8_P29','Median even count','Нахождение медианы при чётном количестве данных','Найдите медиану ряда 2, 4, 6, 8',4,'apply',8,8,
 'Найдите медиану ряда 2, 4, 6, 8','Нахождение среднего двух центральных значений','Medium (Level B)',NULL),
('G8_S29_05','L4','G8_P29','Compare data characteristics','Сравнение характеристик данных','Для ряда 2, 3, 3, 5, 10 найдите среднее, моду и медиану',5,'analyze',8,8,
 'Для ряда 2, 3, 3, 5, 10 найдите среднее, моду и медиану','Комплексный анализ числового ряда','High (Level C)',NULL);

-- ─── П.30: Решение комбинаторных задач методом перебора (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S30_01','L4','G8_P30','Enumerate combinations','Перебор возможных комбинаций','Сколько двузначных чисел можно составить из цифр 1 и 2',1,'apply',8,8,
 'Сколько двузначных чисел можно составить из цифр 1 и 2','Систематический перебор вариантов','Medium (Level B)',NULL),
('G8_S30_02','L4','G8_P30','Enumerate with condition','Перебор вариантов с условием','Сколько двузначных чисел можно составить из цифр 1, 2, 3 без повторений',2,'apply',8,8,
 'Сколько двузначных чисел можно составить из цифр 1, 2, 3 без повторений','Учёт ограничения на повторение элементов','Medium (Level B)',NULL),
('G8_S30_03','L4','G8_P30','Enumerate with table','Перебор вариантов с таблицей','Сколько различных пар можно составить из букв A, B, C',3,'apply',8,8,
 'Сколько различных пар можно составить из букв A, B, C','Использование таблицы или схемы вариантов','Medium (Level B)',NULL),
('G8_S30_04','L4','G8_P30','Enumerate clothing','Перебор в задачах на одежду','У ученика есть 3 рубашки и 2 пары брюк. Сколько разных комплектов',4,'apply',8,8,
 'У ученика есть 3 рубашки и 2 пары брюк. Сколько разных комплектов','Перечисление всех возможных комбинаций','Medium (Level B)',NULL),
('G8_S30_05','L4','G8_P30','Verify completeness','Проверка полноты перебора','Найдите количество всех вариантов при бросании двух монет',5,'analyze',8,8,
 'Найдите количество всех вариантов при бросании двух монет','Систематический перебор исходов','High (Level C)',NULL);

-- ─── П.31: Основной закон комбинаторики и его применение (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G8_S31_01','L4','G8_P31','Product rule','Применение правила произведения','У ученика есть 3 рубашки и 4 пары брюк. Сколько различных комплектов',1,'apply',8,8,
 'У ученика есть 3 рубашки и 4 пары брюк. Сколько различных комплектов','Применение основного закона комбинаторики','Medium (Level B)','m×n'),
('G8_S31_02','L4','G8_P31','Multiple actions','Применение закона для нескольких действий','Сколько трёхзначных чисел можно составить из цифр 1, 2, 3',2,'analyze',8,8,
 'Сколько трёхзначных чисел можно составить из цифр 1, 2, 3','Использование правила произведения для нескольких этапов выбора','High (Level C)',NULL),
('G8_S31_03','L4','G8_P31','Without repetitions','Комбинаторика без повторений','Сколько трёхзначных чисел можно составить из цифр 1, 2, 3 без повторений',3,'analyze',8,8,
 'Сколько трёхзначных чисел можно составить из цифр 1, 2, 3 без повторений','Учёт уменьшения числа вариантов на каждом шаге','High (Level C)',NULL),
('G8_S31_04','L4','G8_P31','With repetitions','Комбинаторика с повторениями','Сколько трёхзначных чисел можно составить из цифр 1 и 2, если повторения разрешены',4,'analyze',8,8,
 'Сколько трёхзначных чисел можно составить из цифр 1 и 2, если повторения разрешены','Применение правила произведения при повторении элементов','High (Level C)',NULL),
('G8_S31_05','L4','G8_P31','With constraint','Комбинаторная задача с ограничением','Сколько трёхзначных чисел можно составить из цифр 1, 2, 3, если первая цифра не может быть 3',5,'analyze',8,8,
 'Сколько трёхзначных чисел можно составить из цифр 1, 2, 3, если первая цифра не может быть 3','Учёт дополнительных условий при подсчёте вариантов','High (Level C)',NULL);
