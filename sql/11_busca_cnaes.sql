-- Busca exploratória nas descrições de CNAE pelos termos do briefing.
-- strip_accents + lower para não depender de acentuação na consulta.
SELECT codigo, descricao
FROM cnaes
WHERE regexp_matches(
        lower(strip_accents(descricao)),
        'music|instrumento|som|sonoriza|gravacao|luthier|palco|ensino|arte|audio|disco|fonograf|espetaculo|reparacao'
      )
ORDER BY codigo;
