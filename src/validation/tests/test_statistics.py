from validation.statistics import fisher_exact_test



def test_fisher_exact_zero_cell_preserves_valid_p_value_without_non_finite_statistic() -> None:
    result = fisher_exact_test([[10, 0], [0, 10]])

    assert result.statistic is None
    assert result.effect_size is None
    assert result.p_value is not None
    assert result.significant is True
    assert result.notes is not None
    assert "infinite" in result.notes
