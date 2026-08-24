-- Mapa vertical -> CNAE. CONFIRMADO com o cliente em 2026-08-24 sobre os volumes
-- reais de estabelecimentos ativos (ver saida/checkpoint-fase1.md, seção 7).
--
-- Duas correções sobre a lista original, ambas aprovadas:
--   * 7739099 -> 7739003: o chute era o "resto" genérico da família (aluguel de
--     máquina industrial, 40.881 ativos); 7739003 é literalmente "aluguel de
--     palcos e coberturas".
--   * 7729299 -> 7729202: mesma história; 7729202 cita instrumentos musicais no
--     próprio texto do CNAE.
-- E dois acréscimos: 4756300 (lojas de instrumentos) e 5912002 (mixagem sonora).
--
-- ALTERADO em 2026-08-24, a pedido: 4756300 SAIU de assistência técnica e virou
-- vertical própria, 'lojas-de-instrumentos-musicais'. Motivo: loja é loja e
-- conserto é conserto, e manter o mesmo CNAE nas duas geraria ~95.775 empresas
-- listadas em duas categorias — páginas quase idênticas por cidade, que buscador
-- trata como conteúdo duplicado.
--
-- REMOVIDO em 2026-08-24, a pedido: o CNAE 9529199 ("Reparação e manutenção de
-- outros objetos e equipamentos pessoais e domésticos não especificados
-- anteriormente"). Era o catch-all que respondia por 92,6 % da vertical luthier e
-- 21,1 % da assistência técnica, quase todo ruído. Consequência medida: luthier
-- cai para o CNAE 3220500 puro, ou seja, fabricação de instrumentos musicais.
--
-- A relação estabelecimento x vertical continua N:N: um estabelecimento com
-- 4756300 principal e 5920100 secundário entra em duas verticais.

CREATE OR REPLACE TABLE vertical_cnae AS
SELECT * FROM (VALUES
    ('assistencia-tecnica',  'Assistência técnica',    '9521500'),
    ('assistencia-tecnica',  'Assistência técnica',    '3319800'),
    ('lojas-de-instrumentos-musicais', 'Lojas de instrumentos musicais', '4756300'),
    ('luthier',              'Luthiers',               '3220500'),
    ('escolas-de-musica',    'Escolas de música',      '8592903'),
    ('estudios-de-gravacao', 'Estúdios de gravação',   '5920100'),
    ('estudios-de-gravacao', 'Estúdios de gravação',   '5912002'),
    ('locacao-som-palco',    'Palcos, som e locação',  '9001906'),
    ('locacao-som-palco',    'Palcos, som e locação',  '7739003'),
    ('locacao-som-palco',    'Palcos, som e locação',  '7729202')
) AS t(vertical, rotulo, cnae);

-- Trava de sanidade: todo CNAE do mapa tem que existir na tabela da RFB.
-- Um código digitado errado sairia como vertical vazia, silenciosamente.
CREATE OR REPLACE VIEW vertical_cnae_invalido AS
SELECT v.vertical, v.cnae
FROM vertical_cnae v
LEFT JOIN cnaes c ON c.codigo = v.cnae
WHERE c.codigo IS NULL;
