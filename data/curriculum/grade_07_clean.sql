-- ============================================================================
-- ALGO V1 — СКЕЛЕТ 7 КЛАСС (чистый методический файл)
-- Источник: Sardor Bozorov, PDF программа 7 класса
-- 3 разделов, 7 тем, 38 пунктов, 111 атомарных навыков
-- ============================================================================
-- ФОРМАТ: Только поля методиста. ИИ-поля (importance, typical_time_seconds,
-- irt_*, difficulty_score, weight, criticality) заполняются пайплайном.
-- Prerequisites — будут сгенерированы AI-пайплайном
-- ============================================================================

-- Очистка
DELETE FROM tasks_master WHERE skill_id LIKE 'G7_%';
DELETE FROM knowledge_hierarchy WHERE id LIKE 'G7_%';

-- ============================================================================
-- L1: РАЗДЕЛЫ (3)
-- ============================================================================
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, class_level_start, class_level_end, sequence_order)
VALUES
    ('G7_NUMEXPR',  'L1', NULL, 'Numeric and Algebraic Expressions', 'Числовые и буквенные выражения', 7, 7, 1),
    ('G7_EQFUNC',  'L1', NULL, 'Equations and Functions', 'Уравнения, системы уравнений и функции', 7, 7, 2),
    ('G7_COMB',  'L1', NULL, 'Combinatorics', 'Комбинаторика', 7, 7, 3);

-- ============================================================================
-- L2: ТЕМЫ (7)
-- ============================================================================
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, class_level_start, class_level_end, sequence_order)
VALUES
    ('G7_T01', 'L2', 'G7_NUMEXPR', 'Algebraic Expressions and Powers', 'Алгебраические выражения и степень', 7, 7, 1),
    ('G7_T02', 'L2', 'G7_NUMEXPR', 'Factoring Formulas', 'Формулы сокращённого умножения', 7, 7, 2),
    ('G7_T03', 'L2', 'G7_NUMEXPR', 'Algebraic Fractions', 'Алгебраические дроби', 7, 7, 3),
    ('G7_T04', 'L2', 'G7_EQFUNC', 'Linear Equations', 'Линейные уравнения', 7, 7, 4),
    ('G7_T05', 'L2', 'G7_EQFUNC', 'Linear Function', 'Линейная функция', 7, 7, 5),
    ('G7_T06', 'L2', 'G7_EQFUNC', 'Systems of Linear Equations', 'Системы линейных уравнений', 7, 7, 6),
    ('G7_T07', 'L2', 'G7_COMB', 'Working with Data', 'Работа с данными', 7, 7, 7);

-- ============================================================================
-- L3: ПУНКТЫ (38)
-- ============================================================================
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, class_level_start, class_level_end, sequence_order)
VALUES
    -- Тема 1
    ('G7_P01', 'L3', 'G7_T01', 'Numeric Expressions', 'Числовые выражения', 7, 7, 1),
    ('G7_P02', 'L3', 'G7_T01', 'Algebraic Expressions', 'Алгебраические выражения', 7, 7, 2),
    ('G7_P03', 'L3', 'G7_T01', 'Algebraic Equalities and Formulas', 'Алгебраические равенства, формулы', 7, 7, 3),
    ('G7_P04', 'L3', 'G7_T01', 'Expanding Brackets and Coefficient', 'Правила раскрытия скобок, коэффициент', 7, 7, 4),
    ('G7_P05', 'L3', 'G7_T01', 'Properties of Arithmetic Operations', 'Свойства арифметических действий', 7, 7, 5),
    ('G7_P06', 'L3', 'G7_T01', 'Power with Natural Exponent', 'Степень с натуральным показателем', 7, 7, 6),
    ('G7_P07', 'L3', 'G7_T01', 'Properties of Powers', 'Свойства степени с натуральным показателем', 7, 7, 7),
    ('G7_P08', 'L3', 'G7_T01', 'Monomial and Standard Form', 'Одночлен и его стандартный вид', 7, 7, 8),
    ('G7_P09', 'L3', 'G7_T01', 'Multiplication and Division of Monomials', 'Умножение и деление одночленов', 7, 7, 9),
    ('G7_P10', 'L3', 'G7_T01', 'Polynomials', 'Многочлены', 7, 7, 10),
    ('G7_P11', 'L3', 'G7_T01', 'Like Terms and Combining', 'Подобные члены и их приведение', 7, 7, 11),
    ('G7_P12', 'L3', 'G7_T01', 'Addition and Subtraction of Polynomials', 'Сложение и вычитание многочленов', 7, 7, 12),
    ('G7_P13', 'L3', 'G7_T01', 'Multiplication of Polynomials', 'Умножение многочленов', 7, 7, 13),
    ('G7_P14', 'L3', 'G7_T01', 'Division of Polynomials', 'Деление многочленов', 7, 7, 14),
    ('G7_P15', 'L3', 'G7_T01', 'Factoring Polynomials', 'Разложение многочленов на множители', 7, 7, 15),
    -- Тема 2
    ('G7_P16', 'L3', 'G7_T02', 'Square of Sum and Difference', 'Квадрат суммы и разности', 7, 7, 16),
    ('G7_P17', 'L3', 'G7_T02', 'Difference of Squares', 'Разность квадратов', 7, 7, 17),
    ('G7_P18', 'L3', 'G7_T02', 'Cube of Sum', 'Куб суммы', 7, 7, 18),
    ('G7_P19', 'L3', 'G7_T02', 'Sum and Difference of Cubes', 'Разность и сумма кубов', 7, 7, 19),
    ('G7_P20', 'L3', 'G7_T02', 'Methods of Factoring', 'Способы разложения на множители', 7, 7, 20),
    ('G7_P21', 'L3', 'G7_T02', 'Applying Factoring Formulas', 'Применение формул сокращённого умножения', 7, 7, 21),
    -- Тема 3
    ('G7_P22', 'L3', 'G7_T03', 'Algebraic Fraction and Reduction', 'Алгебраическая дробь. Сокращение дробей', 7, 7, 22),
    ('G7_P23', 'L3', 'G7_T03', 'Common Denominator', 'Приведение алгебраических дробей к общему знаменателю', 7, 7, 23),
    ('G7_P24', 'L3', 'G7_T03', 'Addition and Subtraction of Algebraic Fractions', 'Сложение и вычитание алгебраических дробей', 7, 7, 24),
    ('G7_P25', 'L3', 'G7_T03', 'Multiplication and Division of Algebraic Fractions', 'Умножение и деление алгебраических дробей', 7, 7, 25),
    -- Тема 4
    ('G7_P26', 'L3', 'G7_T04', 'Equation and Its Root', 'Уравнение и его корень', 7, 7, 26),
    ('G7_P27', 'L3', 'G7_T04', 'Linear Equations with One Unknown', 'Линейные уравнения с одним неизвестным', 7, 7, 27),
    ('G7_P28', 'L3', 'G7_T04', 'Al-Khwarizmi Method', 'Способ решения уравнений аль-Хорезми', 7, 7, 28),
    ('G7_P29', 'L3', 'G7_T04', 'Solving Word Problems with Equations', 'Решение задач с помощью уравнений', 7, 7, 29),
    -- Тема 5
    ('G7_P30', 'L3', 'G7_T05', 'Cartesian Coordinate System', 'Декартова система координат', 7, 7, 30),
    ('G7_P31', 'L3', 'G7_T05', 'Concept of Function', 'Понятие функции', 7, 7, 31),
    ('G7_P32', 'L3', 'G7_T05', 'Linear Function', 'Линейная функция', 7, 7, 32),
    -- Тема 6
    ('G7_P33', 'L3', 'G7_T06', 'Systems of Linear Equations', 'Системы линейных уравнений', 7, 7, 33),
    ('G7_P34', 'L3', 'G7_T06', 'Methods of Solving Systems', 'Способы решения систем линейных уравнений', 7, 7, 34),
    ('G7_P35', 'L3', 'G7_T06', 'Word Problems with Systems', 'Решение задач с помощью систем линейных уравнений', 7, 7, 35),
    -- Тема 7
    ('G7_P36', 'L3', 'G7_T07', 'Basic Combinatorics Rules', 'Основные правила комбинаторики', 7, 7, 36),
    ('G7_P37', 'L3', 'G7_T07', 'Types of Combinatorial Problems', 'Виды комбинаторных задач', 7, 7, 37),
    ('G7_P38', 'L3', 'G7_T07', 'Methods for Combinatorial Problems', 'Способы решения комбинаторных задач', 7, 7, 38);

-- ============================================================================
-- L4: АТОМАРНЫЕ НАВЫКИ (111)
-- Каждый навык содержит: example_task, assessed_ability, difficulty_level, formula из PDF
-- ============================================================================

-- ─── П.1: Числовые выражения (4 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S01_01','L4','G7_P01','Order of operations','Соблюдение порядка действий','Найдите значение выражения 8 + 3 × 2',1,'recall',7,7,
 'Найдите значение выражения 8 + 3 × 2','Выполнение действий в правильном порядке','Low (Level A)',NULL),
('G7_S01_02','L4','G7_P01','Working with brackets','Работа со скобками','Найдите значение выражения (10 − 4) × 3',2,'recall',7,7,
 'Найдите значение выражения (10 − 4) × 3','Выполнение действий сначала в скобках','Low (Level A)',NULL),
('G7_S01_03','L4','G7_P01','Mixed operations','Смешанные действия','Найдите значение выражения 15 − 6 : 2 + 4',3,'apply',7,7,
 'Найдите значение выражения 15 − 6 : 2 + 4','Правильное сочетание деления и сложения','Medium (Level B)',NULL),
('G7_S01_04','L4','G7_P01','Complex numeric expression','Сложное числовое выражение','Найдите значение выражения (18 − 3 × 2) : 3 + 5',4,'analyze',7,7,
 'Найдите значение выражения (18 − 3 × 2) : 3 + 5','Соблюдение полного порядка действий','High (Level C)',NULL);

-- ─── П.2: Алгебраические выражения (4 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S02_01','L4','G7_P02','Identify coefficient','Определение коэффициента','Найдите коэффициент в выражении 7a',1,'recall',7,7,
 'Найдите коэффициент в выражении 7a','Выделение числового коэффициента','Low (Level A)',NULL),
('G7_S02_02','L4','G7_P02','Substitute variable value','Подстановка значения переменной','Найдите значение выражения 3x + 2 при x = 4',2,'apply',7,7,
 'Найдите значение выражения 3x + 2 при x = 4','Подстановка числового значения в выражение','Medium (Level B)',NULL),
('G7_S02_03','L4','G7_P02','Multiple variables','Работа с несколькими переменными','Найдите значение выражения 2a + 3b при a = 1, b = 2',3,'apply',7,7,
 'Найдите значение выражения 2a + 3b при a = 1, b = 2','Вычисление выражения с двумя переменными','Medium (Level B)',NULL),
('G7_S02_04','L4','G7_P02','Simplify expression','Упрощение выражения','Упростите выражение 4x + 3 − x',4,'analyze',7,7,
 'Упростите выражение 4x + 3 − x','Приведение подобных слагаемых','High (Level C)',NULL);

-- ─── П.3: Алгебраические равенства, формулы (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S03_01','L4','G7_P03','Substitute into formula','Подстановка в формулу','Найдите S по формуле S = ab, если a = 5, b = 3',1,'recall',7,7,
 'Найдите S по формуле S = ab, если a = 5, b = 3','Применение формулы для вычисления','Low (Level A)','S=ab'),
('G7_S03_02','L4','G7_P03','Check equality','Проверка равенства','Верно ли равенство 2x + 3 = 7 при x = 2',2,'apply',7,7,
 'Верно ли равенство 2x + 3 = 7 при x = 2','Проверка истинности равенства','Medium (Level B)',NULL),
('G7_S03_03','L4','G7_P03','Express variable from formula','Выражение переменной из формулы','Из формулы S = ab выразите a',3,'analyze',7,7,
 'Из формулы S = ab выразите a','Преобразование формулы','High (Level C)','a=S/b');

-- ─── П.4: Правила раскрытия скобок, коэффициент (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S04_01','L4','G7_P04','Expand brackets','Раскрытие скобок','Раскройте скобки: 3(x + 4)',1,'apply',7,7,
 'Раскройте скобки: 3(x + 4)','Применение распределительного свойства','Medium (Level B)','a(b+c)=ab+ac'),
('G7_S04_02','L4','G7_P04','Minus before brackets','Минус перед скобками','Раскройте скобки: −2(x − 5)',2,'apply',7,7,
 'Раскройте скобки: −2(x − 5)','Правильная работа со знаком минус','Medium (Level B)','-a(b+c)=-ab-ac'),
('G7_S04_03','L4','G7_P04','Two brackets','Две скобки','Упростите выражение 2(x + 3) − 4(x − 1)',3,'analyze',7,7,
 'Упростите выражение 2(x + 3) − 4(x − 1)','Раскрытие нескольких скобок и приведение подобных','High (Level C)',NULL);

-- ─── П.5: Свойства арифметических действий (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S05_01','L4','G7_P05','Commutative property','Применение переместительного свойства','Упростите выражение 7 + 5 + 3, используя удобную перестановку',1,'recall',7,7,
 'Упростите выражение 7 + 5 + 3, используя удобную перестановку','Рациональное применение свойств сложения','Low (Level A)','a+b=b+a'),
('G7_S05_02','L4','G7_P05','Associative property','Применение сочетательного свойства','Вычислите (4 · 25) · 2 удобным способом',2,'apply',7,7,
 'Вычислите (4 · 25) · 2 удобным способом','Группировка множителей','Medium (Level B)','(ab)c=a(bc)'),
('G7_S05_03','L4','G7_P05','Distributive property','Распределительное свойство','Вычислите 6 · 101',3,'analyze',7,7,
 'Вычислите 6 · 101','Представление числа в виде суммы','High (Level C)','a(b+c)=ab+ac');

-- ─── П.6: Степень с натуральным показателем (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S06_01','L4','G7_P06','Compute power','Вычисление степени','Найдите значение 2⁵',1,'recall',7,7,
 'Найдите значение 2⁵','Понимание определения степени','Low (Level A)','aⁿ=a·a·...·a (n раз)'),
('G7_S06_02','L4','G7_P06','Write product as power','Запись произведения в виде степени','Представьте произведение 7 · 7 · 7 в виде степени',2,'apply',7,7,
 'Представьте произведение 7 · 7 · 7 в виде степени','Переход от произведения к степени','Medium (Level B)',NULL),
('G7_S06_03','L4','G7_P06','Power with variable','Степень с переменной','Вычислите a³ при a = 2',3,'apply',7,7,
 'Вычислите a³ при a = 2','Вычисление степени с подстановкой','Medium (Level B)',NULL);

-- ─── П.7: Свойства степени с натуральным показателем (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S07_01','L4','G7_P07','Multiply powers','Умножение степеней','Упростите a³ · a²',1,'apply',7,7,
 'Упростите a³ · a²','Применение правила сложения показателей','Medium (Level B)','aᵐ·aⁿ=aᵐ⁺ⁿ'),
('G7_S07_02','L4','G7_P07','Divide powers','Деление степеней','Упростите x⁵ : x²',2,'apply',7,7,
 'Упростите x⁵ : x²','Вычитание показателей','Medium (Level B)','aᵐ:aⁿ=aᵐ⁻ⁿ'),
('G7_S07_03','L4','G7_P07','Power of power','Степень степени','Упростите (b²)³',3,'analyze',7,7,
 'Упростите (b²)³','Умножение показателей','High (Level C)','(aᵐ)ⁿ=aᵐⁿ');

-- ─── П.8: Одночлен и его стандартный вид (2 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S08_01','L4','G7_P08','Identify monomial','Определение одночлена','Является ли выражение 5x²y одночленом?',1,'recall',7,7,
 'Является ли выражение 5x²y одночленом?','Распознавание одночлена','Low (Level A)',NULL),
('G7_S08_02','L4','G7_P08','Standard form of monomial','Приведение к стандартному виду','Представьте выражение 3x · 2x² в стандартном виде',2,'apply',7,7,
 'Представьте выражение 3x · 2x² в стандартном виде','Умножение коэффициентов и степеней','Medium (Level B)',NULL);

-- ─── П.9: Умножение и деление одночленов (2 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S09_01','L4','G7_P09','Multiply monomials','Умножение одночленов','Умножьте 2a³ · 4a²',1,'apply',7,7,
 'Умножьте 2a³ · 4a²','Применение свойств степеней','Medium (Level B)',NULL),
('G7_S09_02','L4','G7_P09','Divide monomials','Деление одночленов','Разделите 12x⁵ : 3x²',2,'analyze',7,7,
 'Разделите 12x⁵ : 3x²','Деление коэффициентов и вычитание степеней','High (Level C)',NULL);

-- ─── П.10: Многочлены (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S10_01','L4','G7_P10','Identify polynomial','Определение многочлена','Является ли выражение 4x² − 3x + 7 многочленом',1,'recall',7,7,
 'Является ли выражение 4x² − 3x + 7 многочленом','Распознавание структуры многочлена','Low (Level A)',NULL),
('G7_S10_02','L4','G7_P10','Degree of polynomial','Определение степени многочлена','Найдите степень многочлена 5x³ − 2x² + x',2,'apply',7,7,
 'Найдите степень многочлена 5x³ − 2x² + x','Определение наибольшей степени переменной','Medium (Level B)',NULL),
('G7_S10_03','L4','G7_P10','Evaluate polynomial','Вычисление значения многочлена','Найдите значение 2x² − 3x + 1 при x = 2',3,'apply',7,7,
 'Найдите значение 2x² − 3x + 1 при x = 2','Подстановка значения переменной','Medium (Level B)',NULL);

-- ─── П.11: Подобные члены и их приведение (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S11_01','L4','G7_P11','Find like terms','Нахождение подобных членов','Найдите подобные члены в выражении 3a² + 5a − 2a² + a',1,'recall',7,7,
 'Найдите подобные члены в выражении 3a² + 5a − 2a² + a','Группировка подобных членов','Low (Level A)',NULL),
('G7_S11_02','L4','G7_P11','Combine like terms','Приведение подобных членов','Упростите выражение 6x² − 4x + 2x² + x',2,'apply',7,7,
 'Упростите выражение 6x² − 4x + 2x² + x','Сложение и вычитание коэффициентов','Medium (Level B)',NULL),
('G7_S11_03','L4','G7_P11','Multiple groups of like terms','Приведение нескольких групп','Упростите выражение 3a²b + 2ab² − a²b + 5ab²',3,'analyze',7,7,
 'Упростите выражение 3a²b + 2ab² − a²b + 5ab²','Аккуратная работа с разными буквенными частями','High (Level C)',NULL);

-- ─── П.12: Сложение и вычитание многочленов (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S12_01','L4','G7_P12','Add polynomials','Сложение многочленов','Сложите (3x + 5) + (2x − 1)',1,'apply',7,7,
 'Сложите (3x + 5) + (2x − 1)','Раскрытие скобок','Medium (Level B)',NULL),
('G7_S12_02','L4','G7_P12','Subtract polynomials','Вычитание многочленов','Вычтите (2a − 3) из (5a + 4)',2,'apply',7,7,
 'Вычтите (2a − 3) из (5a + 4)','Правильное раскрытие скобок со знаком минус','Medium (Level B)',NULL),
('G7_S12_03','L4','G7_P12','Multiple variables in polynomials','Несколько переменных','Упростите (3x² − x + 2) − (x² + 4x − 1)',3,'analyze',7,7,
 'Упростите (3x² − x + 2) − (x² + 4x − 1)','Аккуратное приведение подобных','High (Level C)',NULL);

-- ─── П.13: Умножение многочленов (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S13_01','L4','G7_P13','Multiply monomial by polynomial','Умножение одночлена на многочлен','Упростите 3x(x + 4)',1,'apply',7,7,
 'Упростите 3x(x + 4)','Применение распределительного свойства','Medium (Level B)','(a+b)(c+d)=ac+ad+bc+bd'),
('G7_S13_02','L4','G7_P13','Multiply binomials','Умножение двучлена на двучлен','Упростите (x + 2)(x + 3)',2,'analyze',7,7,
 'Упростите (x + 2)(x + 3)','Раскрытие двух скобок','High (Level C)',NULL),
('G7_S13_03','L4','G7_P13','Negative coefficients in multiplication','Работа с отрицательными коэффициентами','Упростите (2x − 5)(x − 4)',3,'analyze',7,7,
 'Упростите (2x − 5)(x − 4)','Контроль знаков при умножении','High (Level C)',NULL);

-- ─── П.14: Деление многочленов (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S14_01','L4','G7_P14','Divide by monomial','Деление на одночлен','Разделите (6x² − 3x) на 3x',1,'apply',7,7,
 'Разделите (6x² − 3x) на 3x','Деление каждого члена','Medium (Level B)',NULL),
('G7_S14_02','L4','G7_P14','Check division by multiplication','Проверка деления обратным умножением','Проверьте результат деления умножением',2,'apply',7,7,
 'Проверьте результат деления умножением','Контроль правильности вычислений','Medium (Level B)',NULL),
('G7_S14_03','L4','G7_P14','Divide complex expression','Деление сложного выражения','Разделите (8a³b − 4a²b) на 4a²b',3,'analyze',7,7,
 'Разделите (8a³b − 4a²b) на 4a²b','Применение свойств степеней','High (Level C)',NULL);

-- ─── П.15: Разложение многочленов на множители (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S15_01','L4','G7_P15','Factor out common factor','Вынесение общего множителя','Разложите на множители 6x + 9',1,'apply',7,7,
 'Разложите на множители 6x + 9','Нахождение общего множителя','Medium (Level B)',NULL),
('G7_S15_02','L4','G7_P15','Grouping','Группировка','Разложите на множители ax + ay',2,'apply',7,7,
 'Разложите на множители ax + ay','Вынесение общего множителя из группы','Medium (Level B)',NULL),
('G7_S15_03','L4','G7_P15','Difference of squares formula','Применение формулы разности квадратов','Разложите x² − 9',3,'analyze',7,7,
 'Разложите x² − 9','Применение формулы a² − b² = (a − b)(a + b)','High (Level C)','a²−b²=(a−b)(a+b)');

-- ─── П.16: Квадрат суммы и разности (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S16_01','L4','G7_P16','Square of sum formula','Применение формулы квадрата суммы','Упростите (x + 3)²',1,'apply',7,7,
 'Упростите (x + 3)²','Применение формулы (a + b)²','Medium (Level B)','(a+b)²=a²+2ab+b²'),
('G7_S16_02','L4','G7_P16','Square of difference formula','Применение формулы квадрата разности','Упростите (a − 5)²',2,'apply',7,7,
 'Упростите (a − 5)²','Правильная работа со знаком перед 2ab','Medium (Level B)','(a−b)²=a²−2ab+b²'),
('G7_S16_03','L4','G7_P16','Variables in square formula','Работа с переменными','Упростите (2x + y)²',3,'analyze',7,7,
 'Упростите (2x + y)²','Аккуратное вычисление удвоенного произведения','High (Level C)',NULL);

-- ─── П.17: Разность квадратов (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S17_01','L4','G7_P17','Recognize difference of squares','Узнавание формулы','Разложите на множители x² − 16',1,'apply',7,7,
 'Разложите на множители x² − 16','Распознавание разности квадратов','Medium (Level B)','a²−b²=(a−b)(a+b)'),
('G7_S17_02','L4','G7_P17','Variables in difference of squares','Работа с переменными','Разложите на множители 9a² − b²',2,'apply',7,7,
 'Разложите на множители 9a² − b²','Представление 9a² как (3a)²','Medium (Level B)',NULL),
('G7_S17_03','L4','G7_P17','Complex difference of squares','Сложное выражение','Разложите 4x² − 25y²',3,'analyze',7,7,
 'Разложите 4x² − 25y²','Корректное применение формулы','High (Level C)',NULL);

-- ─── П.18: Куб суммы (2 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S18_01','L4','G7_P18','Cube of sum formula','Применение формулы куба суммы','Упростите (x + 2)³',1,'analyze',7,7,
 'Упростите (x + 2)³','Применение формулы с четырьмя членами','High (Level C)','(a+b)³=a³+3a²b+3ab²+b³'),
('G7_S18_02','L4','G7_P18','Cube of sum with coefficient','Работа с коэффициентом','Упростите (2a + b)³',2,'analyze',7,7,
 'Упростите (2a + b)³','Правильное возведение в степень одночлена','High (Level C)',NULL);

-- ─── П.19: Разность и сумма кубов (2 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S19_01','L4','G7_P19','Factor difference of cubes','Разложение разности кубов','Разложите x³ − 8',1,'analyze',7,7,
 'Разложите x³ − 8','Представление 8 как 2³','High (Level C)','a³−b³=(a−b)(a²+ab+b²)'),
('G7_S19_02','L4','G7_P19','Factor sum of cubes','Разложение суммы кубов','Разложите a³ + 27',2,'analyze',7,7,
 'Разложите a³ + 27','Применение формулы суммы кубов','High (Level C)','a³+b³=(a+b)(a²−ab+b²)');

-- ─── П.20: Способы разложения на множители (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S20_01','L4','G7_P20','Factor out common factor','Вынесение общего множителя','Разложите 5x² + 10x',1,'apply',7,7,
 'Разложите 5x² + 10x','Нахождение общего множителя','Medium (Level B)',NULL),
('G7_S20_02','L4','G7_P20','Grouping method','Группировка','Разложите ax + ay + bx + by',2,'analyze',7,7,
 'Разложите ax + ay + bx + by','Разложение способом группировки','High (Level C)',NULL),
('G7_S20_03','L4','G7_P20','Choose factoring method','Выбор способа','Разложите x² − 5x',3,'apply',7,7,
 'Разложите x² − 5x','Определение подходящего метода','Medium (Level B)',NULL);

-- ─── П.21: Применение формул сокращённого умножения (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S21_01','L4','G7_P21','Recognize formula in expression','Узнавание формулы в выражении','Упростите (x − 7)(x + 7)',1,'apply',7,7,
 'Упростите (x − 7)(x + 7)','Применение формулы разности квадратов','Medium (Level B)',NULL),
('G7_S21_02','L4','G7_P21','Simplify complex with formulas','Упрощение сложного выражения','Упростите (a + b)² − (a − b)²',2,'analyze',7,7,
 'Упростите (a + b)² − (a − b)²','Применение нескольких формул','High (Level C)',NULL),
('G7_S21_03','L4','G7_P21','Compute using formulas','Вычисление удобным способом','Найдите 49², используя формулу (a − b)²',3,'analyze',7,7,
 'Найдите 49², используя формулу (a − b)²','Применение формулы для вычислений','High (Level C)','(a−b)²=a²−2ab+b²');

-- ─── П.22: Алгебраическая дробь. Сокращение дробей (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S22_01','L4','G7_P22','Identify algebraic fraction','Определение алгебраической дроби','Является ли выражение (3x + 2)/5 алгебраической дробью',1,'recall',7,7,
 'Является ли выражение (3x + 2)/5 алгебраической дробью','Распознавание структуры дроби','Low (Level A)',NULL),
('G7_S22_02','L4','G7_P22','Reduce numeric factor','Сокращение числового множителя','Сократите дробь 6x/9',2,'apply',7,7,
 'Сократите дробь 6x/9','Деление числителя и знаменателя на общий делитель','Medium (Level B)',NULL),
('G7_S22_03','L4','G7_P22','Reduce variables','Сокращение переменных','Сократите дробь 8x²/(4x)',3,'analyze',7,7,
 'Сократите дробь 8x²/(4x)','Применение свойств степеней при сокращении','High (Level C)',NULL);

-- ─── П.23: Приведение алгебраических дробей к общему знаменателю (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S23_01','L4','G7_P23','Find common denominator','Нахождение общего знаменателя','Приведите к общему знаменателю дроби 1/x и 1/y',1,'apply',7,7,
 'Приведите к общему знаменателю дроби 1/x и 1/y','Нахождение произведения знаменателей','Medium (Level B)',NULL),
('G7_S23_02','L4','G7_P23','Common denominator with coefficients','Приведение с числовыми коэффициентами','Приведите дроби 2/x и 3/(2x) к общему знаменателю',2,'analyze',7,7,
 'Приведите дроби 2/x и 3/(2x) к общему знаменателю','Правильное домножение дробей','High (Level C)',NULL),
('G7_S23_03','L4','G7_P23','Expressions in denominator','Работа с выражениями в знаменателе','Приведите к общему знаменателю 1/(x − 1) и 1/(x + 1)',3,'analyze',7,7,
 'Приведите к общему знаменателю 1/(x − 1) и 1/(x + 1)','Формирование общего знаменателя (x − 1)(x + 1)','High (Level C)',NULL);

-- ─── П.24: Сложение и вычитание алгебраических дробей (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S24_01','L4','G7_P24','Add fractions same denominator','Сложение с одинаковым знаменателем','Сложите (3/x) + (5/x)',1,'apply',7,7,
 'Сложите (3/x) + (5/x)','Сложение числителей','Medium (Level B)','a/b+c/b=(a+c)/b'),
('G7_S24_02','L4','G7_P24','Subtract fractions same denominator','Вычитание с одинаковым знаменателем','Вычтите (7/x) − (2/x)',2,'apply',7,7,
 'Вычтите (7/x) − (2/x)','Вычитание числителей','Medium (Level B)',NULL),
('G7_S24_03','L4','G7_P24','Add fractions different denominators','Сложение с разными знаменателями','Сложите 1/x + 1/y',3,'analyze',7,7,
 'Сложите 1/x + 1/y','Приведение к общему знаменателю','High (Level C)',NULL);

-- ─── П.25: Умножение и деление алгебраических дробей (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S25_01','L4','G7_P25','Multiply fractions','Умножение дробей','Перемножьте (2/x) · (3/y)',1,'apply',7,7,
 'Перемножьте (2/x) · (3/y)','Перемножение числителей и знаменателей','Medium (Level B)','(a/b)·(c/d)=ac/(bd)'),
('G7_S25_02','L4','G7_P25','Divide fractions','Деление дробей','Разделите (4/x) : (2/y)',2,'analyze',7,7,
 'Разделите (4/x) : (2/y)','Переход к умножению на обратную дробь','High (Level C)','(a/b):(c/d)=(a/b)·(d/c)'),
('G7_S25_03','L4','G7_P25','Reduce after multiplication','Сокращение после умножения','Упростите (6x/5) · (5/(3x))',3,'analyze',7,7,
 'Упростите (6x/5) · (5/(3x))','Сокращение переменных и чисел','High (Level C)',NULL);

-- ─── П.26: Уравнение и его корень (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S26_01','L4','G7_P26','Identify equation','Определение уравнения','Является ли выражение 3x + 5 = 11 уравнением',1,'recall',7,7,
 'Является ли выражение 3x + 5 = 11 уравнением','Распознавание равенства с переменной','Low (Level A)',NULL),
('G7_S26_02','L4','G7_P26','Check root','Проверка корня уравнения','Является ли число 2 корнем уравнения 4x = 8',2,'apply',7,7,
 'Является ли число 2 корнем уравнения 4x = 8','Подстановка значения в уравнение','Medium (Level B)',NULL),
('G7_S26_03','L4','G7_P26','Find root','Нахождение корня уравнения','Найдите корень уравнения x + 7 = 12',3,'apply',7,7,
 'Найдите корень уравнения x + 7 = 12','Выполнение обратного действия','Medium (Level B)',NULL);

-- ─── П.27: Линейные уравнения с одним неизвестным (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S27_01','L4','G7_P27','Transfer term','Перенос слагаемого','Решите уравнение 3x − 5 = 7',1,'apply',7,7,
 'Решите уравнение 3x − 5 = 7','Перенос числа с изменением знака','Medium (Level B)',NULL),
('G7_S27_02','L4','G7_P27','Variables on both sides','Уравнение с коэффициентами по обе стороны','Решите уравнение 4x − 2 = 2x + 6',2,'analyze',7,7,
 'Решите уравнение 4x − 2 = 2x + 6','Перенос переменных в одну сторону','High (Level C)',NULL),
('G7_S27_03','L4','G7_P27','Equation with brackets','Уравнение со скобками','Решите уравнение 2(x + 3) = 5x − 4',3,'analyze',7,7,
 'Решите уравнение 2(x + 3) = 5x − 4','Раскрытие скобок и приведение подобных','High (Level C)',NULL);

-- ─── П.28: Способ решения уравнений аль-Хорезми (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S28_01','L4','G7_P28','Same operation both sides','Применение одинаковых действий','Решите уравнение x + 4 = 9',1,'recall',7,7,
 'Решите уравнение x + 4 = 9','Выполнение одного и того же действия с обеими частями','Low (Level A)',NULL),
('G7_S28_02','L4','G7_P28','Divide both sides','Деление обеих частей на число','Решите уравнение 5x = 20',2,'apply',7,7,
 'Решите уравнение 5x = 20','Деление обеих частей уравнения','Medium (Level B)',NULL),
('G7_S28_03','L4','G7_P28','Multi-step equation','Многошаговое уравнение','Решите уравнение 3x + 5 = 2x + 12',3,'analyze',7,7,
 'Решите уравнение 3x + 5 = 2x + 12','Последовательное применение действий к обеим частям','High (Level C)',NULL);

-- ─── П.29: Решение задач с помощью уравнений (2 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S29_01','L4','G7_P29','Simple word problem','Простая текстовая задача','Число увеличили на 8 и получили 15. Найдите число',1,'apply',7,7,
 'Число увеличили на 8 и получили 15. Найдите число','Составление линейного уравнения','Medium (Level B)',NULL),
('G7_S29_02','L4','G7_P29','Sum of two numbers','Задача на сумму двух чисел','Сумма двух чисел равна 20. Одно число на 4 больше другого. Найдите числа',2,'analyze',7,7,
 'Сумма двух чисел равна 20. Одно число на 4 больше другого. Найдите числа','Построение уравнения по условию','High (Level C)',NULL);

-- ─── П.30: Декартова система координат (2 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S30_01','L4','G7_P30','Identify coordinates','Определение координат точки','Назовите координаты точки (3; −2)',1,'recall',7,7,
 'Назовите координаты точки (3; −2)','Правильное чтение координат','Low (Level A)',NULL),
('G7_S30_02','L4','G7_P30','Plot point','Построение точки','Постройте точку (−4; 1)',2,'apply',7,7,
 'Постройте точку (−4; 1)','Движение сначала по оси x, затем по оси y','Medium (Level B)',NULL);

-- ─── П.31: Понятие функции (2 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S31_01','L4','G7_P31','Build value table','Построение таблицы значений','Составьте таблицу значений для y = 2x',1,'apply',7,7,
 'Составьте таблицу значений для y = 2x','Вычисление зависимых значений','Medium (Level B)',NULL),
('G7_S31_02','L4','G7_P31','Check if relation is function','Проверка, является ли зависимость функцией','Может ли одному значению x соответствовать два значения y',2,'apply',7,7,
 'Может ли одному значению x соответствовать два значения y','Понимание определения функции','Medium (Level B)',NULL);

-- ─── П.32: Линейная функция (7 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S32_01','L4','G7_P32','Identify coefficients','Определение коэффициентов','Найдите k и b в функции y = 3x − 2',1,'recall',7,7,
 'Найдите k и b в функции y = 3x − 2','Выделение коэффициентов','Low (Level A)','y=kx+b'),
('G7_S32_02','L4','G7_P32','Plot linear function','Построение графика линейной функции','Постройте график функции y = x + 1',2,'analyze',7,7,
 'Постройте график функции y = x + 1','Построение таблицы значений и нанесение точек','High (Level C)',NULL),
('G7_S32_03','L4','G7_P32','Increasing or decreasing','Определение характера функции','Определите, возрастает или убывает функция y = −2x + 3',3,'analyze',7,7,
 'Определите, возрастает или убывает функция y = −2x + 3','Анализ знака коэффициента k','High (Level C)',NULL),
('G7_S32_04','L4','G7_P32','Point on graph','Проверка принадлежности точки графику','Принадлежит ли точка (2; 5) графику функции y = 2x + 1',4,'apply',7,7,
 'Принадлежит ли точка (2; 5) графику функции y = 2x + 1','Подстановка координат точки в формулу функции','Medium (Level B)',NULL),
('G7_S32_05','L4','G7_P32','Y-axis intersection','Нахождение точки пересечения с осью Oy','Найдите точку пересечения графика функции y = 4x − 3 с осью Oy',5,'apply',7,7,
 'Найдите точку пересечения графика функции y = 4x − 3 с осью Oy','Определение значения функции при x = 0','Medium (Level B)',NULL),
('G7_S32_06','L4','G7_P32','X-axis intersection','Нахождение точки пересечения с осью Ox','Найдите точку пересечения графика функции y = 2x − 4 с осью Ox',6,'analyze',7,7,
 'Найдите точку пересечения графика функции y = 2x − 4 с осью Ox','Решение уравнения 0 = kx + b','High (Level C)',NULL),
('G7_S32_07','L4','G7_P32','Intersection of two linear functions','Нахождение точки пересечения двух линейных функций','Найдите точку пересечения функций y = 2x + 1 и y = x + 4',7,'analyze',7,7,
 'Найдите точку пересечения функций y = 2x + 1 и y = x + 4','Приравнивание выражений и решение линейного уравнения','High (Level C)',NULL);

-- ─── П.33: Системы линейных уравнений (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S33_01','L4','G7_P33','Check system solution','Определение решения системы','Является ли пара (3; 2) решением системы x + y = 5, x − y = 1',1,'apply',7,7,
 'Является ли пара (3; 2) решением системы x + y = 5, x − y = 1','Подстановка значений в оба уравнения','Medium (Level B)',NULL),
('G7_S33_02','L4','G7_P33','Geometric meaning','Геометрический смысл решения','Сколько решений имеет система, если прямые пересекаются',2,'apply',7,7,
 'Сколько решений имеет система, если прямые пересекаются','Понимание связи с графиками','Medium (Level B)',NULL),
('G7_S33_03','L4','G7_P33','Number of solutions','Определение количества решений','Сколько решений имеет система двух совпадающих прямых',3,'analyze',7,7,
 'Сколько решений имеет система двух совпадающих прямых','Анализ взаимного положения прямых','High (Level C)',NULL);

-- ─── П.34: Способы решения систем линейных уравнений (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S34_01','L4','G7_P34','Substitution method','Метод подстановки','Решите систему x = 5 − y, 2x + y = 7',1,'analyze',7,7,
 'Решите систему x = 5 − y, 2x + y = 7','Подстановка выражения в уравнение','High (Level C)',NULL),
('G7_S34_02','L4','G7_P34','Addition method','Метод сложения','Решите систему 2x + y = 7, 2x − y = 3',2,'analyze',7,7,
 'Решите систему 2x + y = 7, 2x − y = 3','Сложение уравнений для исключения переменной','High (Level C)',NULL),
('G7_S34_03','L4','G7_P34','Graphical method','Графический способ','Найдите решение системы y = x + 1, y = 3',3,'apply',7,7,
 'Найдите решение системы y = x + 1, y = 3','Нахождение точки пересечения графиков','Medium (Level B)',NULL);

-- ─── П.35: Решение задач с помощью систем линейных уравнений (2 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S35_01','L4','G7_P35','Sum and difference problem','Задача на сумму и разность','Сумма двух чисел равна 20, их разность равна 4. Найдите числа',1,'analyze',7,7,
 'Сумма двух чисел равна 20, их разность равна 4. Найдите числа','Составление и решение системы','High (Level C)',NULL),
('G7_S35_02','L4','G7_P35','Motion problem','Задача на движение','Два автомобиля выехали навстречу друг другу со скоростями 60 и 80 км/ч. Расстояние 280 км. Через сколько часов встретятся',2,'analyze',7,7,
 'Два автомобиля выехали навстречу друг другу со скоростями 60 и 80 км/ч. Расстояние 280 км. Через сколько часов встретятся','Составление системы или уравнения по условию','High (Level C)',NULL);

-- ─── П.36: Основные правила комбинаторики (2 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S36_01','L4','G7_P36','Product rule','Правило произведения','Сколько различных пар можно составить из 3 рубашек и 4 брюк',1,'apply',7,7,
 'Сколько различных пар можно составить из 3 рубашек и 4 брюк','Применение правила произведения','Medium (Level B)',NULL),
('G7_S36_02','L4','G7_P36','Sum rule','Правило суммы','Есть 5 красных и 3 синих шара. Сколько способов выбрать один шар',2,'recall',7,7,
 'Есть 5 красных и 3 синих шара. Сколько способов выбрать один шар','Применение правила суммы','Low (Level A)',NULL);

-- ─── П.37: Виды комбинаторных задач (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S37_01','L4','G7_P37','Permutations','Перестановки без повторений','Сколькими способами можно переставить буквы в слове «ТОК»',1,'apply',7,7,
 'Сколькими способами можно переставить буквы в слове «ТОК»','Понимание факториала n!','Medium (Level B)','n!'),
('G7_S37_02','L4','G7_P37','Arrangements','Размещения','Сколькими способами можно выбрать и упорядочить 2 книги из 5',2,'analyze',7,7,
 'Сколькими способами можно выбрать и упорядочить 2 книги из 5','Применение формулы размещений','High (Level C)','A(n,k)=n!/(n−k)!'),
('G7_S37_03','L4','G7_P37','Combinations','Сочетания','Сколькими способами можно выбрать 2 книги из 5',3,'analyze',7,7,
 'Сколькими способами можно выбрать 2 книги из 5','Применение формулы сочетаний','High (Level C)','C(n,k)=n!/(k!(n−k)!)');

-- ─── П.38: Способы решения комбинаторных задач (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G7_S38_01','L4','G7_P38','Tree of variants','Использование дерева вариантов','Найдите число способов выбрать одежду, используя схему вариантов',1,'apply',7,7,
 'Найдите число способов выбрать одежду, используя схему вариантов','Построение дерева вариантов','Medium (Level B)',NULL),
('G7_S38_02','L4','G7_P38','Use formulas','Использование формул','Найдите C(6,2)',2,'analyze',7,7,
 'Найдите C(6,2)','Применение формулы сочетаний','High (Level C)',NULL),
('G7_S38_03','L4','G7_P38','Choose method','Выбор правильного метода','Определите, что применить — перестановку, размещение или сочетание',3,'analyze',7,7,
 'Определите, что применить — перестановку, размещение или сочетание','Анализ условия задачи','High (Level C)',NULL);
